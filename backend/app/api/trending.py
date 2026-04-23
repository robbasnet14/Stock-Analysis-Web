from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.dependencies import get_optional_user
from app.models.user import User
from app.models.watchlist import Watchlist
from app.config import get_settings
from app.schemas.analytics import TrendingItemOut
from app.state import state


router = APIRouter(prefix="/market", tags=["market"])
settings = get_settings()


async def _universe(db: AsyncSession, user: User | None) -> list[str]:
    if user is not None:
        stmt = select(Watchlist).where(Watchlist.user_id == user.id).order_by(Watchlist.symbol.asc())
        rows = [r.symbol for r in (await db.execute(stmt)).scalars().all()]
        if rows:
            return rows
    return settings.ticker_list


@router.get("/trending", response_model=list[TrendingItemOut])
async def market_trending(
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> list[TrendingItemOut]:
    tickers = await _universe(db, user)
    payload = await state.trending_service.get_trending(db, tickers, redis_client=state.redis)
    return [TrendingItemOut(**item) for item in payload["items"]]
