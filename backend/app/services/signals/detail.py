from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news import NewsArticle
from app.models.symbol import SymbolMaster
from app.services.signals.backtest import compute_projection
from app.services.signals.ensemble import compute_ensemble
from app.services.signals.levels import compute_key_levels
from app.services.signals.technical import _series_from_rows, compute_technical


def _label_from_score(score: float) -> str:
    if score > 0.2:
        return "BULLISH"
    if score < -0.2:
        return "BEARISH"
    return "NEUTRAL"


def _infer_asset_class(ticker: str, symbol_type: str | None) -> str:
    symbol = ticker.upper()
    if "-USD" in symbol or symbol.endswith("USDT"):
        return "crypto"
    raw = (symbol_type or "").lower()
    if "etf" in raw or "fund" in raw:
        return "etf"
    return "equity"


def _build_quote_view(symbol: str, payload: dict[str, Any]) -> dict[str, float]:
    price = float(payload.get("price") or 0.0)
    change_percent = float(payload.get("change_percent") or 0.0)
    previous_close = price / (1.0 + (change_percent / 100.0)) if price > 0 and change_percent != -100 else price
    change = price - previous_close
    return {
        "price": round(price, 2),
        "change": round(change, 2),
        "change_percent": round(change_percent, 2),
    }


def _technical_rules(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in payload.get("indicators") or []:
        vote = float(row.get("vote") or 0.0)
        weight = float(row.get("weight") or 0.0)
        rows.append(
            {
                "rule": str(row.get("name") or ""),
                "value": round(float(row.get("value") or 0.0), 4),
                "vote": vote,
                "weight": weight,
                "fired": abs(vote) > 0,
                "explanation": str(row.get("explanation") or row.get("fired_rule") or ""),
            }
        )
    return rows


def _ensemble_rules(payload: dict[str, Any]) -> list[dict[str, Any]]:
    weights = payload.get("weights") or {}
    contributions = payload.get("contributions") or {}
    models = payload.get("models") or {}
    rules: list[dict[str, Any]] = []
    for key, weight in weights.items():
        value = float(models.get(key) or 0.0)
        vote = 1.0 if value > 0.1 else -1.0 if value < -0.1 else 0.0
        pretty = key.replace("_model", "").replace("_", " ")
        rules.append(
            {
                "rule": key,
                "value": round(value, 4),
                "vote": vote,
                "weight": float(weight),
                "fired": abs(value) > 0.05,
                "explanation": f"{pretty.title()} contributed {float(contributions.get(key) or 0.0):+.3f} to the ensemble score.",
            }
        )
    return rules


async def _symbol_meta(db: AsyncSession, ticker: str) -> tuple[str, str]:
    stmt = select(SymbolMaster).where(SymbolMaster.symbol == ticker.upper()).limit(1)
    row = (await db.execute(stmt)).scalars().first()
    if row is None:
        return ticker.upper(), _infer_asset_class(ticker, None)
    return (row.name or row.symbol or ticker.upper()), _infer_asset_class(ticker, row.type)


async def _news_context(db: AsyncSession, ticker: str) -> dict[str, Any]:
    symbol = ticker.upper()
    cutoff = datetime.utcnow() - timedelta(hours=24)
    article_count_stmt = select(func.count()).select_from(NewsArticle).where(NewsArticle.ticker == symbol, NewsArticle.published_at >= cutoff)
    article_count = int((await db.execute(article_count_stmt)).scalar() or 0)

    latest_stmt = (
        select(NewsArticle)
        .where(NewsArticle.ticker == symbol)
        .order_by(NewsArticle.published_at.desc(), NewsArticle.id.desc())
        .limit(5)
    )
    latest_rows = list((await db.execute(latest_stmt)).scalars().all())

    sentiment_stmt = (
        select(NewsArticle.sentiment_score)
        .where(NewsArticle.ticker == symbol, NewsArticle.published_at >= cutoff)
        .order_by(NewsArticle.published_at.desc())
        .limit(100)
    )
    sentiment_rows = [float(v) for v in (await db.execute(sentiment_stmt)).scalars().all() if v is not None]
    sentiment_score = round(sum(sentiment_rows) / len(sentiment_rows), 4) if sentiment_rows else 0.0

    return {
        "sentiment_score": sentiment_score,
        "article_count_24h": article_count,
        "top_articles": [
            {
                "title": row.headline or row.title or symbol,
                "source": row.source or "Unknown",
                "published_at": row.published_at,
                "sentiment": (row.sentiment_label or row.sentiment or "neutral").lower(),
                "url": row.url or "",
            }
            for row in latest_rows
        ],
    }


async def build_signal_detail(*, db: AsyncSession, ticker: str, horizon: str, market_data, redis_client) -> dict[str, Any]:
    symbol = ticker.upper().strip()
    h = (horizon or "short").lower()

    technical, ensemble, quote_payload = await __import__("asyncio").gather(
        compute_technical(db=db, market_data=market_data, redis_client=redis_client, ticker=symbol, horizon=h),
        compute_ensemble(db=db, market_data=market_data, redis_client=redis_client, ticker=symbol, horizon=h),
        market_data.get_quote(symbol),
    )

    company_name, asset_class = await _symbol_meta(db, symbol)
    quote = _build_quote_view(symbol, quote_payload)

    bar_payload = await market_data.get_bars(symbol, "ALL", tf="1Day", max_points=2200)
    frame = _series_from_rows(bar_payload.get("bars") or []).dropna(subset=["timestamp"]).sort_values("timestamp").tail(1500).reset_index(drop=True)

    levels = compute_key_levels(frame, h)
    mini_chart_bars = [
        {
            "timestamp": ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "close": round(float(close), 4),
        }
        for ts, close in zip(frame["timestamp"].tail(30), frame["close"].tail(30), strict=False)
    ]

    technical_verdict = {
        "label": _label_from_score(float(technical.get("score") or 0.0)),
        "score": round(float(technical.get("score") or 0.0), 4),
        "confidence": int(round(float(technical.get("confidence") or 0.0) * 100)),
        "track": "technical",
    }
    ensemble_verdict = {
        "label": _label_from_score(float(ensemble.get("score") or 0.0)),
        "score": round(float(ensemble.get("score") or 0.0), 4),
        "confidence": int(round(float(ensemble.get("confidence") or 0.0) * 100)),
        "track": "ensemble",
    }

    top_level_verdict = ensemble_verdict
    signal_label = technical_verdict["label"].lower()
    if signal_label == "neutral" and ensemble_verdict["label"] != "NEUTRAL":
        signal_label = ensemble_verdict["label"].lower()

    projection = await compute_projection(
        ticker=symbol,
        horizon=h,
        current_price=float(quote["price"] or 0.0),
        signal_label=signal_label,
        market_data=market_data,
        redis_client=redis_client,
    )
    news = await _news_context(db, symbol)
    context = {
        "regime": ensemble.get("regime") or "unknown",
        "regime_context": ensemble.get("regime_context") or {},
        "sector": ensemble.get("sector"),
        "sector_position": ensemble.get("sector_position") or "neutral",
        "next_earnings": ensemble.get("next_earnings"),
        "matched_themes": ensemble.get("matched_themes") or [],
        "extras": ensemble.get("extras") or [],
    }

    return {
        "ticker": symbol,
        "company_name": company_name,
        "asset_class": asset_class,
        "quote": quote,
        "horizon": h,
        "verdict": top_level_verdict,
        "triggered_rules": _ensemble_rules(ensemble),
        "context": context,
        "projection": projection,
        "news": news,
        "levels": levels,
        "mini_chart_bars": mini_chart_bars,
        "signals": {
            "technical": {
                "verdict": technical_verdict,
                "triggered_rules": _technical_rules(technical),
                "explanation": technical.get("explanation") or "",
            },
            "ensemble": {
                "verdict": ensemble_verdict,
                "triggered_rules": _ensemble_rules(ensemble),
                "explanation": ensemble.get("narrative") or "",
            },
        },
    }
