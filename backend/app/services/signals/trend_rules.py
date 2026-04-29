from __future__ import annotations

from typing import Any

import pandas as pd


def _ema(close: pd.Series, period: int) -> pd.Series:
    return close.astype(float).ewm(span=period, adjust=False, min_periods=period).mean()


def evaluate_trend_position(df: pd.DataFrame, horizon: str) -> dict[str, Any]:
    """Evaluate price position relative to multiple EMAs."""
    if df.empty or "close" not in df.columns:
        return {"rules": []}

    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    if len(close) < 5:
        return {"rules": []}

    h = (horizon or "short").lower()
    ema_20 = _ema(close, 20)
    ema_50 = _ema(close, 50)
    ema_200 = _ema(close, 200)

    last = float(close.iloc[-1])
    rules: list[dict[str, Any]] = []

    if pd.notna(ema_200.iloc[-1]) and float(ema_200.iloc[-1]) > 0:
        ema_200_last = float(ema_200.iloc[-1])
        above_200 = last > ema_200_last
        rules.append(
            {
                "rule": "long_term_regime",
                "value": round(last / ema_200_last - 1, 4),
                "vote": 0.5 if above_200 else -0.5,
                "weight": 0.20 if h == "long" else 0.10,
                "fired": True,
                "explanation": (
                    f"Price is {abs(last / ema_200_last - 1) * 100:.1f}% "
                    f"{'above' if above_200 else 'below'} the 200-EMA - "
                    f"{'bullish long-term regime (Stage 2)' if above_200 else 'bearish long-term regime (Stage 4)'}."
                ),
            }
        )

    if pd.notna(ema_50.iloc[-1]) and pd.notna(ema_200.iloc[-1]):
        gc = float(ema_50.iloc[-1]) > float(ema_200.iloc[-1])
        gc_prev = float(ema_50.iloc[-5]) > float(ema_200.iloc[-5]) if len(ema_50) > 5 and pd.notna(ema_50.iloc[-5]) and pd.notna(ema_200.iloc[-5]) else gc
        if gc != gc_prev:
            rules.append(
                {
                    "rule": "golden_cross" if gc else "death_cross",
                    "value": round(float(ema_50.iloc[-1] - ema_200.iloc[-1]), 2),
                    "vote": 1.0 if gc else -1.0,
                    "weight": 0.15,
                    "fired": True,
                    "explanation": (
                        f"50-EMA just crossed {'above' if gc else 'below'} 200-EMA "
                        f"- major {'bullish' if gc else 'bearish'} regime shift."
                    ),
                }
            )

    if pd.notna(ema_20.iloc[-1]) and len(close) >= 5:
        ema_20_last = float(ema_20.iloc[-1])
        recent_low = float(close.tail(5).min())
        tagged_20 = recent_low <= ema_20_last * 1.005
        bouncing = last > float(close.iloc[-2]) and last > ema_20_last
        in_uptrend = pd.notna(ema_50.iloc[-1]) and ema_20_last > float(ema_50.iloc[-1])
        if tagged_20 and bouncing and in_uptrend:
            rules.append(
                {
                    "rule": "ema20_bounce",
                    "value": round(last / ema_20_last - 1, 4),
                    "vote": 0.7,
                    "weight": 0.10,
                    "fired": True,
                    "explanation": "Price tagged 20-EMA support and bounced - classic trend-following buy in uptrends.",
                }
            )

    return {"rules": rules}
