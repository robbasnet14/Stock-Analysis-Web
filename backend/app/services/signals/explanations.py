from __future__ import annotations


def explain_signal(symbol: str, score: float, reasons: list[str]) -> str:
    label = "bullish" if score >= 0.6 else "neutral" if score >= 0.45 else "bearish"
    reason_text = "; ".join(reasons[:4]) if reasons else "mixed factors"
    return f"{symbol.upper()} screens {label} with score {score:.2f}. Drivers: {reason_text}."
