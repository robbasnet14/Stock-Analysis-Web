from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.dependencies import get_optional_user
from app.models.user import User
from app.models.watchlist import Watchlist
from app.config import get_settings
from app.schemas.analytics import EnsembleDiagnosticsItemOut, EnsembleItemOut
from app.state import state


router = APIRouter(prefix="/stocks", tags=["stocks"])
settings = get_settings()


async def _universe(db: AsyncSession, user: User | None) -> list[str]:
    if user is not None:
        stmt = select(Watchlist).where(Watchlist.user_id == user.id).order_by(Watchlist.symbol.asc())
        rows = [r.symbol for r in (await db.execute(stmt)).scalars().all()]
        if rows:
            return rows
    return settings.ticker_list


@router.get("/ensemble-ranking", response_model=list[EnsembleItemOut])
async def ensemble_ranking(
    horizon: str = "short",
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> list[EnsembleItemOut]:
    tickers = await _universe(db, user)
    payload = await state.ensemble_service.get_ensemble_ranking(db, tickers, horizon, redis_client=state.redis)
    return [EnsembleItemOut(**item) for item in payload["items"]]


@router.get("/ensemble-diagnostics", response_model=list[EnsembleDiagnosticsItemOut])
async def ensemble_diagnostics(
    horizon: str = "short",
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> list[EnsembleDiagnosticsItemOut]:
    tickers = await _universe(db, user)
    payload = await state.ensemble_service.get_ensemble_diagnostics(db, tickers, horizon, redis_client=state.redis)
    return [EnsembleDiagnosticsItemOut(**item) for item in payload["items"]]
