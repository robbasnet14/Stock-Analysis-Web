from __future__ import annotations

from typing import Any

import pandas as pd


R_MULTIPLIERS = {
    "short": 1.0,
    "mid": 2.0,
    "long": 3.0,
}


def _recent_local_minimum(lows: list[float]) -> float | None:
    if len(lows) < 5:
        return None
    for idx in range(len(lows) - 3, 1, -1):
        pivot = float(lows[idx])
        if pivot <= float(lows[idx - 1]) and pivot <= float(lows[idx - 2]) and float(lows[idx + 1]) > pivot and float(lows[idx + 2]) > pivot:
            return pivot
    return None


def _recent_local_maximum(highs: list[float]) -> float | None:
    if len(highs) < 5:
        return None
    for idx in range(len(highs) - 3, 1, -1):
        pivot = float(highs[idx])
        if pivot >= float(highs[idx - 1]) and pivot >= float(highs[idx - 2]) and float(highs[idx + 1]) < pivot and float(highs[idx + 2]) < pivot:
            return pivot
    return None


def compute_key_levels(frame: pd.DataFrame, horizon: str) -> dict[str, Any]:
    if frame.empty:
        return {
            "current": 0.0,
            "support": 0.0,
            "resistance": 0.0,
            "suggested_stop": 0.0,
            "suggested_take_profit": 0.0,
            "risk_reward_ratio": 0.0,
        }

    recent = frame.tail(20).copy()
    current = float(recent["close"].iloc[-1])
    lows = [float(x) for x in recent["low"].tolist()]
    highs = [float(x) for x in recent["high"].tolist()]

    support = _recent_local_minimum(lows)
    if support is None:
        support = float(min(lows))

    resistance = _recent_local_maximum(highs)
    if resistance is None:
        resistance = float(max(highs))

    suggested_stop = float(support) * 0.99
    risk_unit = max(current - suggested_stop, current * 0.005)
    multiplier = R_MULTIPLIERS.get((horizon or "short").lower(), 1.0)
    suggested_take_profit = current + (risk_unit * multiplier)
    denom = abs(current - suggested_stop)
    risk_reward_ratio = abs(suggested_take_profit - current) / denom if denom > 0 else 0.0

    return {
        "current": round(current, 4),
        "support": round(float(support), 4),
        "resistance": round(float(resistance), 4),
        "suggested_stop": round(suggested_stop, 4),
        "suggested_take_profit": round(suggested_take_profit, 4),
        "risk_reward_ratio": round(float(risk_reward_ratio), 4),
    }
