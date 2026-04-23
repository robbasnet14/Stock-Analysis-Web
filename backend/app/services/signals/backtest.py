from __future__ import annotations

import json
from datetime import timedelta
from statistics import median
from typing import Any

import numpy as np
import pandas as pd

from app.services.signals.technical import _score, _series_from_rows, _talib_or_fallback, _vote_rows


HORIZON_DAYS = {
    "short": 7,
    "mid": 30,
    "long": 90,
}


def _action_from_score(score: float) -> str:
    if score > 0.2:
        return "bullish"
    if score < -0.2:
        return "bearish"
    return "neutral"


def _accuracy_for_label(label: str, returns_pct: list[float]) -> float:
    if not returns_pct:
        return 0.0
    if label == "bullish":
        wins = sum(1 for value in returns_pct if value > 0)
    elif label == "bearish":
        wins = sum(1 for value in returns_pct if value < 0)
    else:
        wins = sum(1 for value in returns_pct if abs(value) <= 2.0)
    return round((wins / len(returns_pct)) * 100.0, 2)


def _clamp_projection(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(max(-20.0, min(20.0, value))), 2)


async def compute_projection(*, ticker: str, horizon: str, current_price: float, signal_label: str, market_data, redis_client) -> dict[str, Any]:
    symbol = ticker.upper()
    h = (horizon or "short").lower()
    label = (signal_label or "neutral").lower()
    cache_key = f"signals:detail:projection:{symbol}:{h}:{label}"

    if redis_client is not None:
        cached = await redis_client.get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass

    payload = await market_data.get_bars(symbol, "ALL", tf="1Day", max_points=2200)
    frame = _series_from_rows(payload.get("bars") or [])
    frame = frame.dropna(subset=["timestamp"]).sort_values("timestamp").tail(1500).reset_index(drop=True)

    if len(frame) < 60:
        result = {
            "median_return_pct": None,
            "bullish_case_pct": None,
            "bearish_case_pct": None,
            "projected_price_median": None,
            "projected_price_bull": None,
            "projected_price_bear": None,
            "accuracy_pct": 0,
            "sample_size": 0,
            "backtest_start": None,
            "backtest_end": None,
        }
        if redis_client is not None:
            await redis_client.set(cache_key, json.dumps(result), ex=86400)
        return result

    arr = _talib_or_fallback(frame, h)
    hold_days = HORIZON_DAYS.get(h, 7)
    close = frame["close"].astype(float).reset_index(drop=True)
    timestamps = pd.to_datetime(frame["timestamp"], utc=True).reset_index(drop=True)
    returns_pct: list[float] = []

    for idx in range(30, len(frame) - 1):
        sliced = {key: value[: idx + 1] for key, value in arr.items()}
        votes = _vote_rows(sliced)
        if not votes:
            continue
        score, _ = _score(votes)
        action = _action_from_score(score)
        if action != label:
            continue

        target_time = timestamps.iloc[idx] + timedelta(days=hold_days)
        future_idx = timestamps.searchsorted(target_time, side="left")
        if future_idx >= len(close):
            continue

        entry = float(close.iloc[idx])
        future = float(close.iloc[int(future_idx)])
        if entry <= 0 or future <= 0:
            continue

        returns_pct.append(((future / entry) - 1.0) * 100.0)

    sample_size = len(returns_pct)
    backtest_start = timestamps.iloc[0].date().isoformat() if len(timestamps) else None
    backtest_end = timestamps.iloc[-1].date().isoformat() if len(timestamps) else None

    if sample_size < 20:
        result = {
            "median_return_pct": None,
            "bullish_case_pct": None,
            "bearish_case_pct": None,
            "projected_price_median": None,
            "projected_price_bull": None,
            "projected_price_bear": None,
            "accuracy_pct": _accuracy_for_label(label, returns_pct) if returns_pct else 0,
            "sample_size": sample_size,
            "backtest_start": backtest_start,
            "backtest_end": backtest_end,
        }
        if redis_client is not None:
            await redis_client.set(cache_key, json.dumps(result), ex=86400)
        return result

    median_return = _clamp_projection(float(median(returns_pct)))
    bullish_case = _clamp_projection(float(np.percentile(returns_pct, 75)))
    bearish_case = _clamp_projection(float(np.percentile(returns_pct, 25)))

    result = {
        "median_return_pct": median_return,
        "bullish_case_pct": bullish_case,
        "bearish_case_pct": bearish_case,
        "projected_price_median": round(current_price * (1.0 + (median_return or 0.0) / 100.0), 2) if median_return is not None else None,
        "projected_price_bull": round(current_price * (1.0 + (bullish_case or 0.0) / 100.0), 2) if bullish_case is not None else None,
        "projected_price_bear": round(current_price * (1.0 + (bearish_case or 0.0) / 100.0), 2) if bearish_case is not None else None,
        "accuracy_pct": _accuracy_for_label(label, returns_pct),
        "sample_size": sample_size,
        "backtest_start": backtest_start,
        "backtest_end": backtest_end,
    }
    if redis_client is not None:
        await redis_client.set(cache_key, json.dumps(result), ex=86400)
    return result
