from __future__ import annotations

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import delete, select

from app.config import get_settings
from app.db.database import SessionLocal
from app.models.alert import AlertSubscription
from app.models.holdings_lot import HoldingsLot
from app.models.news import NewsArticle
from app.models.watchlist import Watchlist
from app.services.alerts.evaluator import evaluate_alerts_once
from app.services.signals.earnings import get_next_earnings
from app.services.signals.regime import compute_market_regime
from app.services.signals.sector_rotation import compute_sector_strength
from app.services.signals.themes import detect_themes
from app.state import state


logger = logging.getLogger(__name__)
settings = get_settings()


def _market_hours_now() -> bool:
    now = datetime.utcnow()
    return now.weekday() < 5 and 13 <= now.hour <= 21


async def evaluate_alerts_job() -> None:
    async with SessionLocal() as db:
        count = await evaluate_alerts_once(db)
    logger.info("scheduler: evaluate_alerts checked=%s", count)


async def compute_market_regime_job() -> None:
    result = await compute_market_regime(market_data=state.market_data, redis_client=state.redis)
    logger.info("scheduler: compute_market_regime regime=%s", result.get("regime"))


async def compute_sector_strength_job() -> None:
    result = await compute_sector_strength(market_data=state.market_data, redis_client=state.redis)
    logger.info("scheduler: compute_sector_strength sectors=%s", len(result.get("sectors") or {}))


async def detect_themes_job() -> None:
    async with SessionLocal() as db:
        result = await detect_themes(db=db, redis_client=state.redis, window_hours=24)
    logger.info("scheduler: detect_themes hot=%s", ",".join(result.get("hot_themes") or []))


async def warm_signal_cache_for_holdings_job() -> None:
    if not _market_hours_now():
        logger.info("scheduler: warm_signal_cache_for_holdings skipped outside market hours")
        return
    async with SessionLocal() as db:
        lot_rows = list((await db.execute(select(HoldingsLot.ticker).where(HoldingsLot.status == "open").distinct())).scalars().all())
        watch_rows = list((await db.execute(select(Watchlist.symbol).distinct())).scalars().all())
        tickers = sorted({*(str(t).upper() for t in lot_rows), *(str(t).upper() for t in watch_rows), *settings.ticker_list})[:50]
        for ticker in tickers:
            try:
                await state.ml_service.predict(db, ticker)
            except Exception:
                logger.exception("scheduler: signal warm failed ticker=%s", ticker)
    logger.info("scheduler: warm_signal_cache_for_holdings tickers=%s", len(tickers))


async def prune_old_news_job() -> None:
    cutoff = datetime.utcnow() - timedelta(days=30)
    async with SessionLocal() as db:
        result = await db.execute(delete(NewsArticle).where(NewsArticle.published_at < cutoff))
        await db.commit()
    logger.info("scheduler: prune_old_news deleted=%s", result.rowcount or 0)


async def backtest_recompute_job() -> None:
    tickers = sorted(state.watchlist) if state.watchlist else settings.ticker_list
    async with SessionLocal() as db:
        for ticker in tickers[:25]:
            try:
                latest = await state.stock_service.get_latest_quote(db, ticker)
                if latest is not None:
                    await state.ml_service.predict(db, ticker)
            except Exception:
                logger.exception("scheduler: backtest_recompute failed ticker=%s", ticker)
    logger.info("scheduler: backtest_recompute tickers=%s", len(tickers[:25]))


async def update_earnings_calendar_job() -> None:
    async with SessionLocal() as db:
        rows = list((await db.execute(select(AlertSubscription.ticker).where(AlertSubscription.condition_type == "earnings_upcoming").distinct())).scalars().all())
    for ticker in sorted({str(t).upper() for t in rows}):
        try:
            await get_next_earnings(ticker, redis_client=state.redis)
        except Exception:
            logger.exception("scheduler: update_earnings_calendar failed ticker=%s", ticker)
    logger.info("scheduler: update_earnings_calendar tickers=%s", len(rows))


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(evaluate_alerts_job, "interval", seconds=60, id="evaluate_alerts", max_instances=1, coalesce=True)
    scheduler.add_job(compute_market_regime_job, "interval", hours=1, id="compute_market_regime", max_instances=1, coalesce=True)
    scheduler.add_job(compute_sector_strength_job, "interval", hours=4, id="compute_sector_strength", max_instances=1, coalesce=True)
    scheduler.add_job(detect_themes_job, "interval", minutes=30, id="detect_themes", max_instances=1, coalesce=True)
    scheduler.add_job(warm_signal_cache_for_holdings_job, "interval", minutes=15, id="warm_signal_cache_for_holdings", max_instances=1, coalesce=True)
    scheduler.add_job(prune_old_news_job, "cron", hour=3, minute=0, id="prune_old_news", max_instances=1, coalesce=True)
    scheduler.add_job(backtest_recompute_job, "cron", day_of_week="sun", hour=4, minute=0, id="backtest_recompute", max_instances=1, coalesce=True)
    scheduler.add_job(update_earnings_calendar_job, "cron", hour=5, minute=0, id="update_earnings_calendar", max_instances=1, coalesce=True)
    logger.info("scheduler: configured jobs=%s", ",".join(sorted(job.id for job in scheduler.get_jobs())))
    return scheduler
