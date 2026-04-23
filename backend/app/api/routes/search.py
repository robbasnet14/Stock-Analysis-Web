from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.state import state


router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
async def autocomplete(q: str, db: AsyncSession = Depends(get_db)) -> dict:
    rows = await state.stock_service.search_symbols_db(db, q, limit=20)
    if rows:
        return {"results": rows}
    return {"results": await state.market_data.search(q)}
