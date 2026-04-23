from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.schemas.analytics import PortfolioOptimizeIn, PortfolioOptimizeOut
from app.state import state


router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.post("/optimize", response_model=PortfolioOptimizeOut)
async def optimize_portfolio(payload: PortfolioOptimizeIn, db: AsyncSession = Depends(get_db)) -> PortfolioOptimizeOut:
    try:
        result = await state.portfolio_optimizer.optimize(db, payload.symbols)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PortfolioOptimizeOut(**result)
