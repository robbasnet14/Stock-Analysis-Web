from __future__ import annotations


HORIZON_PARAMS = {
    "short": {
        "momentum_days": 5,
        "sentiment_weight": 0.25,
        "cache_ttl": 60,
        "rsi_period": 14,
        "stoch_period": 14,
        "ema_fast": 12,
        "ema_slow": 26,
    },
    "mid": {
        "momentum_days": 20,
        "sentiment_weight": 0.2,
        "cache_ttl": 900,
        "rsi_period": 14,
        "stoch_period": 14,
        "ema_fast": 20,
        "ema_slow": 50,
    },
    "long": {
        "momentum_days": 60,
        "sentiment_weight": 0.15,
        "cache_ttl": 3600,
        "rsi_period": 14,
        "stoch_period": 14,
        "ema_fast": 50,
        "ema_slow": 200,
    },
}


def params_for(horizon: str) -> dict:
    return HORIZON_PARAMS.get((horizon or "short").lower(), HORIZON_PARAMS["short"])
