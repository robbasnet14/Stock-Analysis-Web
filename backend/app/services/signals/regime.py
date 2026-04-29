from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pandas as pd


def _bars_close(bars: list[dict[str, Any]]) -> pd.Series:
    return pd.Series([float(b.get("close") or b.get("price") or 0.0) for b in bars if float(b.get("close") or b.get("price") or 0.0) > 0])


async def compute_market_regime(*, market_data, redis_client=None) -> dict[str, Any]:
    """Compute overall market regime from SPY and VIX. Cache for one hour."""
    cache_key = "regime:current:v1"
    if redis_client is not None:
        cached = await redis_client.get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass

    spy_payload = await market_data.get_bars("SPY", "1Y", tf="1Day")
    spy_close = _bars_close(spy_payload.get("bars") or [])
    if len(spy_close) >= 200:
        spy_ema_200 = float(spy_close.ewm(span=200, adjust=False, min_periods=200).mean().iloc[-1])
        spy_now = float(spy_close.iloc[-1])
    elif len(spy_close):
        spy_now = float(spy_close.iloc[-1])
        spy_ema_200 = float(spy_close.mean())
    else:
        spy_now = 0.0
        spy_ema_200 = 0.0

    spy_above_200 = bool(spy_now > spy_ema_200) if spy_ema_200 > 0 else False

    try:
        vix_payload = await market_data.get_bars("^VIX", "1M", tf="1Day")
        vix_close = _bars_close(vix_payload.get("bars") or [])
        vix_now = float(vix_close.iloc[-1]) if len(vix_close) else 20.0
    except Exception:
        vix_now = 20.0

    if spy_above_200 and vix_now < 20:
        regime = "risk_on"
        signal_modifier = 1.0
    elif spy_above_200 and vix_now < 30:
        regime = "neutral"
        signal_modifier = 0.85
    elif not spy_above_200 and vix_now > 25:
        regime = "risk_off"
        signal_modifier = 0.5
    else:
        regime = "transitional"
        signal_modifier = 0.7

    result = {
        "regime": regime,
        "spy_above_200ema": spy_above_200,
        "spy_ema_200": round(spy_ema_200, 4),
        "spy_close": round(spy_now, 4),
        "vix": round(vix_now, 4),
        "signal_modifier": signal_modifier,
        "computed_at": datetime.utcnow().isoformat(),
    }
    if redis_client is not None:
        await redis_client.setex(cache_key, 3600, json.dumps(result))
    return result
