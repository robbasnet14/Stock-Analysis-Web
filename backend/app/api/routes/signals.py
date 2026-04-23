from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.dependencies import get_optional_user
from app.models.holdings_lot import HoldingsLot
from app.models.watchlist import Watchlist
from app.models.user import User
from app.services.signals.detail import build_signal_detail
from app.services.signals.ensemble import compute_ensemble
from app.services.signals.technical import compute_technical
from app.state import state


router = APIRouter(prefix="/signals", tags=["signals"])


async def _default_tickers(db: AsyncSession, user: User | None) -> list[str]:
    if user is None:
        return ["AAPL", "MSFT", "NVDA", "TSLA", "SPY", "QQQ"]

    rows: list[str] = []
    lot_stmt = select(HoldingsLot.ticker).where(HoldingsLot.user_id == user.id, HoldingsLot.status == "open")
    lot_rows = list((await db.execute(lot_stmt)).scalars().all())
    rows.extend([str(x).upper() for x in lot_rows if x])

    wl_stmt = select(Watchlist.symbol).where(Watchlist.user_id == user.id)
    wl_rows = list((await db.execute(wl_stmt)).scalars().all())
    rows.extend([str(x).upper() for x in wl_rows if x])

    if not rows:
        rows.extend(["AAPL", "BTC-USD", "ETH-USD"])
    return sorted(list(dict.fromkeys(rows)))


@router.get("/bull")
async def bull_signals(horizon: str = "short", db: AsyncSession = Depends(get_db), user: User | None = Depends(get_optional_user)) -> dict:
    tickers = sorted(state.watchlist) if state.watchlist else ["AAPL", "MSFT", "TSLA", "NVDA", "AMZN"]
    items = await state.stock_service.get_bull_cases_horizon(db, tickers, horizon=horizon)
    return {"horizon": horizon.lower(), "items": items}


@router.get("/ensemble")
async def ensemble_signals(horizon: str = "short", db: AsyncSession = Depends(get_db), user: User | None = Depends(get_optional_user)) -> dict:
    tickers = sorted(state.watchlist) if state.watchlist else ["AAPL", "MSFT", "TSLA", "NVDA", "AMZN"]
    data = await state.ensemble_service.rank(db, tickers, horizon=horizon)
    return {"horizon": horizon.lower(), "items": data}


@router.get("")
async def batch_signals(
    track: str = "technical",
    horizon: str = "short",
    tickers: str = "",
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> dict:
    names = [x.strip().upper() for x in (tickers or "").split(",") if x.strip()]
    if not names:
        names = await _default_tickers(db, user)

    items = []
    if track.lower() == "technical":
        for t in names:
            items.append(
                await compute_technical(
                    db=db,
                    market_data=state.market_data,
                    redis_client=state.redis,
                    ticker=t,
                    horizon=horizon,
                )
            )
    else:
        for t in names:
            items.append(
                await compute_ensemble(
                    db=db,
                    market_data=state.market_data,
                    redis_client=state.redis,
                    ticker=t,
                    horizon=horizon,
                )
            )
    return {"track": track.lower(), "horizon": horizon.lower(), "items": items}


@router.get("/technical/{ticker}")
async def technical_signal(
    ticker: str,
    horizon: str = "short",
    db: AsyncSession = Depends(get_db),
    _: User | None = Depends(get_optional_user),
) -> dict:
    return await compute_technical(
        db=db,
        market_data=state.market_data,
        redis_client=state.redis,
        ticker=ticker,
        horizon=horizon,
    )


@router.get("/ensemble/{ticker}")
async def ensemble_signal(
    ticker: str,
    horizon: str = "short",
    db: AsyncSession = Depends(get_db),
    _: User | None = Depends(get_optional_user),
) -> dict:
    return await compute_ensemble(
        db=db,
        market_data=state.market_data,
        redis_client=state.redis,
        ticker=ticker,
        horizon=horizon,
    )


@router.get("/detail/{ticker}")
async def signal_detail(
    ticker: str,
    horizon: str = "short",
    db: AsyncSession = Depends(get_db),
    _: User | None = Depends(get_optional_user),
) -> dict:
    return await build_signal_detail(
        db=db,
        ticker=ticker,
        horizon=horizon,
        market_data=state.market_data,
        redis_client=state.redis,
    )
