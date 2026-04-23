from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timedelta
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news import NewsArticle
from app.services.signals.horizons import params_for
from app.services.signals.technical import compute_technical


INDICATOR_WEIGHTS: dict[str, float] = {
    "technical_model": 0.45,
    "sentiment_model": 0.25,
    "momentum_model": 0.20,
    "risk_model": 0.10,
}


def _cache_ttl(horizon: str) -> int:
    cfg = params_for(horizon)
    base = int(cfg.get("cache_ttl", 60))
    return base + random.randint(0, 30)


def _clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return float(max(lo, min(hi, v)))


async def _sentiment_24h(db: AsyncSession, ticker: str) -> float:
    cutoff = datetime.utcnow() - timedelta(hours=24)
    stmt = (
        select(NewsArticle.sentiment_score)
        .where(NewsArticle.ticker == ticker.upper(), NewsArticle.published_at >= cutoff)
        .order_by(NewsArticle.published_at.desc())
        .limit(100)
    )
    values = [float(v) for v in (await db.execute(stmt)).scalars().all() if v is not None]
    if not values:
        return 0.0
    return _clamp(float(np.mean(values)))


def _momentum_from_bars(bars: list[dict[str, Any]], horizon: str) -> float:
    if len(bars) < 3:
        return 0.0
    close = np.array([float(b.get("close") or b.get("price") or 0.0) for b in bars], dtype=float)
    close = close[close > 0]
    if len(close) < 3:
        return 0.0
    cfg = params_for(horizon)
    n = int(cfg.get("momentum_days", 5))
    lookback = max(2, min(len(close) - 1, n))
    ret = (close[-1] / close[-1 - lookback]) - 1.0
    return _clamp(float(np.tanh(ret * 8.0)))


def _risk_from_bars(bars: list[dict[str, Any]]) -> float:
    if len(bars) < 10:
        return 0.0
    close = np.array([float(b.get("close") or b.get("price") or 0.0) for b in bars], dtype=float)
    close = close[close > 0]
    if len(close) < 10:
        return 0.0
    rets = np.diff(np.log(close))
    vol = float(np.std(rets)) if len(rets) else 0.0
    # Lower volatility should improve ensemble score, so risk component is inverted.
    return _clamp(1.0 - np.tanh(vol * 20.0), 0.0, 1.0)


async def compute_ensemble(
    *,
    db: AsyncSession,
    market_data,
    redis_client,
    ticker: str,
    horizon: str,
) -> dict[str, Any]:
    symbol = ticker.upper()
    h = (horizon or "short").lower()
    cache_key = f"signals:{symbol}:{h}:ensemble"
    lock_key = f"{cache_key}:lock"
    ttl = _cache_ttl(h)

    if redis_client is not None:
        cached = await redis_client.get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass

    lock_acquired = False
    if redis_client is not None:
        try:
            lock_acquired = bool(await redis_client.set(lock_key, "1", ex=15, nx=True))
            if not lock_acquired:
                await asyncio.sleep(0.1)
                cached = await redis_client.get(cache_key)
                if cached:
                    return json.loads(cached)
        except Exception:
            lock_acquired = False

    technical = await compute_technical(db=db, market_data=market_data, redis_client=redis_client, ticker=symbol, horizon=h)
    bars_payload = await market_data.get_bars(symbol, "1M" if h == "short" else "3M" if h == "mid" else "1Y")
    bars = bars_payload.get("bars") or []

    technical_score = _clamp(float(technical.get("score", 0.0)))
    if technical.get("status") == "insufficient_data":
        technical_score = 0.0
    sentiment_score = await _sentiment_24h(db, symbol)
    momentum_score = _momentum_from_bars(bars, h)
    risk_score = _risk_from_bars(bars)

    contributions = {
        "technical_model": round(technical_score * INDICATOR_WEIGHTS["technical_model"], 6),
        "sentiment_model": round(sentiment_score * INDICATOR_WEIGHTS["sentiment_model"], 6),
        "momentum_model": round(momentum_score * INDICATOR_WEIGHTS["momentum_model"], 6),
        "risk_model": round(risk_score * INDICATOR_WEIGHTS["risk_model"], 6),
    }

    final_score = _clamp(sum(contributions.values()))
    confidence = float(
        max(
            0.0,
            min(
                1.0,
                1.0
                - float(np.std([technical_score, sentiment_score, momentum_score]))
                + (0.15 if len(bars) > 120 else 0.0),
            ),
        )
    )
    confidence = max(0.05, min(0.98, confidence))

    narrative = (
        f"{symbol} ensemble ({h}) combines technical ({technical_score:.2f}), "
        f"sentiment ({sentiment_score:.2f}), momentum ({momentum_score:.2f}), and risk ({risk_score:.2f}) "
        f"into final score {final_score:.2f} with confidence {confidence:.2f}."
    )

    payload = {
        "ticker": symbol,
        "horizon": h,
        "track": "ensemble",
        "score": round(final_score, 6),
        "confidence": round(confidence, 6),
        "contributions": contributions,
        "weights": INDICATOR_WEIGHTS,
        "narrative": narrative,
        "models": {
            "technical_model": round(technical_score, 6),
            "sentiment_model": round(sentiment_score, 6),
            "momentum_model": round(momentum_score, 6),
            "risk_model": round(risk_score, 6),
        },
        "as_of": datetime.utcnow().isoformat(),
    }

    if redis_client is not None:
        await redis_client.set(cache_key, json.dumps(payload), ex=ttl)
        if lock_acquired:
            await redis_client.delete(lock_key)
    return payload
