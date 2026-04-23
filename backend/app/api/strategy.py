from fastapi import APIRouter, Depends, HTTPException
import json
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.models.backtest_run import BacktestRun
from app.state import state


router = APIRouter(prefix="/strategy", tags=["strategy"])


class BacktestIn(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=24)
    strategy: str = "rsi_oversold"
    lookback_days: int = Field(default=252 * 2, ge=90, le=252 * 10)


@router.post("/backtest")
async def backtest_strategy(payload: BacktestIn, db: AsyncSession = Depends(get_db)) -> dict:
    result = await state.stock_service.run_backtest(
        db,
        symbol=payload.symbol,
        strategy=payload.strategy,
        lookback_days=payload.lookback_days,
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])

    db.add(
        BacktestRun(
            symbol=result["symbol"],
            strategy=result["strategy"],
            lookback_days=int(result.get("lookback_days", payload.lookback_days)),
            trades=int(result.get("trades", 0)),
            win_rate=float(result.get("win_rate", 0.0)),
            avg_return=float(result.get("avg_return", 0.0)),
            max_drawdown=float(result.get("max_drawdown", 0.0)),
            cumulative_return=float(result.get("cumulative_return", 0.0)),
            meta_json=json.dumps({"source": "api", "params": payload.model_dump()}, default=str),
        )
    )
    await db.commit()
    return result


@router.get("/backtest/history")
async def backtest_history(
    symbol: str | None = None,
    strategy: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> dict:
    lim = max(1, min(500, int(limit)))
    stmt = select(BacktestRun).order_by(BacktestRun.created_at.desc()).limit(lim)
    if symbol:
        stmt = stmt.where(BacktestRun.symbol == symbol.upper())
    if strategy:
        stmt = stmt.where(BacktestRun.strategy == strategy)
    rows = list((await db.execute(stmt)).scalars().all())
    return {
        "items": [
            {
                "id": r.id,
                "symbol": r.symbol,
                "strategy": r.strategy,
                "lookback_days": r.lookback_days,
                "trades": r.trades,
                "win_rate": r.win_rate,
                "avg_return": r.avg_return,
                "max_drawdown": r.max_drawdown,
                "cumulative_return": r.cumulative_return,
                "created_at": r.created_at,
            }
            for r in rows
        ]
    }


@router.get("/backtest/history/{run_id}")
async def backtest_run_detail(run_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    row = await db.get(BacktestRun, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    meta = {}
    try:
        meta = json.loads(row.meta_json or "{}")
    except Exception:
        meta = {}
    return {
        "id": row.id,
        "symbol": row.symbol,
        "strategy": row.strategy,
        "lookback_days": row.lookback_days,
        "trades": row.trades,
        "win_rate": row.win_rate,
        "avg_return": row.avg_return,
        "max_drawdown": row.max_drawdown,
        "cumulative_return": row.cumulative_return,
        "meta": meta,
        "created_at": row.created_at,
    }
