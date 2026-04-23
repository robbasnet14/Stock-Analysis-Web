from datetime import datetime
from fastapi import APIRouter
from app.state import state


router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("/flow/{ticker}")
async def flow_snapshot(ticker: str):
    data = await state.provider_aggregator.get_snapshot(ticker)
    return data


@router.get("/status")
async def provider_status() -> dict:
    return {
        "checked_at": datetime.utcnow().isoformat(),
        "providers": state.market_data.provider_health(),
    }


@router.get("/cache-health")
async def cache_health() -> dict:
    redis = state.redis
    if redis is None:
        return {"ok": False, "redis_connected": False, "error": "Redis client not initialized"}

    try:
        started = datetime.utcnow()
        pong = await redis.ping()
        latency_ms = (datetime.utcnow() - started).total_seconds() * 1000.0
        key_count = await redis.dbsize()
        return {
            "ok": bool(pong),
            "redis_connected": bool(pong),
            "latency_ms": round(latency_ms, 2),
            "db_keys": int(key_count or 0),
        }
    except Exception as exc:
        return {"ok": False, "redis_connected": False, "error": str(exc)}
