from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.dependencies import get_optional_user
from app.models.user import User
from app.models.watchlist import Watchlist
from sqlalchemy import select
from app.config import get_settings
from app.state import state


router = APIRouter(prefix="/market", tags=["market"])
settings = get_settings()


async def _market_universe(db: AsyncSession, user: User | None) -> list[str]:
    if user is not None:
        stmt = select(Watchlist).where(Watchlist.user_id == user.id).order_by(Watchlist.symbol.asc())
        rows = [r.symbol for r in (await db.execute(stmt)).scalars().all()]
        if rows:
            return rows
    return settings.ticker_list


@router.get("/pulse")
async def market_pulse(
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> dict:
    universe = await _market_universe(db, user)
    data = await state.stock_service.get_market_pulse(db, universe)
    return data
