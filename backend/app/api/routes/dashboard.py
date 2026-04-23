from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.dependencies import get_optional_user
from app.models.user import User
from app.state import state


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/live")
async def dashboard_live() -> dict:
    return {
        "providers": state.market_data.provider_health(),
        "watchlist_size": len(state.watchlist),
        "timestamp": datetime.utcnow(),
    }


@router.get("/timeseries")
async def dashboard_timeseries(
    ticker: str = "AAPL",
    range: str = "1D",
    db: AsyncSession = Depends(get_db),
    _: User | None = Depends(get_optional_user),
) -> dict:
    rows = await state.market_data.get_candles(ticker, range)
    return {"ticker": ticker.upper(), "range": range.upper(), "data": rows}
