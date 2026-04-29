from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.services.signals.regime import compute_market_regime
from app.services.signals.sector_rotation import compute_sector_strength
from app.services.signals.themes import detect_themes
from app.state import state


router = APIRouter(tags=["signal-context"])


@router.get("/regime")
async def regime() -> dict:
    return await compute_market_regime(market_data=state.market_data, redis_client=state.redis)


@router.get("/sectors/strength")
async def sectors_strength() -> dict:
    return await compute_sector_strength(market_data=state.market_data, redis_client=state.redis)


@router.get("/themes/hot")
async def themes_hot(db: AsyncSession = Depends(get_db)) -> dict:
    data = await detect_themes(db=db, redis_client=state.redis, window_hours=24)
    hot = data.get("hot_themes") or []
    return {
        "hot_themes": hot[:5],
        "themes": {name: data.get("themes", {}).get(name) for name in hot[:5]},
        "computed_at": data.get("computed_at"),
    }
