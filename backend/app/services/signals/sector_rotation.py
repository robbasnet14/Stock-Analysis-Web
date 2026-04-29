from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pandas as pd


SECTOR_ETFS = {
    "tech": "XLK",
    "semis": "SOXX",
    "ai_robotics": "BOTZ",
    "energy": "XLE",
    "financials": "XLF",
    "healthcare": "XLV",
    "consumer_disc": "XLY",
    "consumer_staples": "XLP",
    "industrials": "XLI",
    "materials": "XLB",
    "utilities": "XLU",
    "real_estate": "XLRE",
    "comm": "XLC",
}

TICKER_SECTOR = {
    "AAPL": "tech",
    "MSFT": "tech",
    "GOOG": "tech",
    "GOOGL": "tech",
    "META": "comm",
    "NVDA": "semis",
    "AMD": "semis",
    "TSM": "semis",
    "INTC": "semis",
    "AVGO": "semis",
    "MU": "semis",
    "SOXX": "semis",
    "TSLA": "consumer_disc",
    "AMZN": "consumer_disc",
    "JPM": "financials",
    "BAC": "financials",
    "SOFI": "financials",
    "XOM": "energy",
    "CVX": "energy",
    "UNH": "healthcare",
    "LLY": "healthcare",
}


def _close_series(bars: list[dict[str, Any]]) -> pd.Series:
    return pd.Series([float(b.get("close") or b.get("price") or 0.0) for b in bars if float(b.get("close") or b.get("price") or 0.0) > 0])


def _relative_return(series: pd.Series, spy: pd.Series, periods: int) -> float:
    if len(series) <= periods or len(spy) <= periods:
        return 0.0
    return float((series.iloc[-1] / series.iloc[-1 - periods] - 1.0) - (spy.iloc[-1] / spy.iloc[-1 - periods] - 1.0))


async def compute_sector_strength(*, market_data, redis_client=None) -> dict[str, Any]:
    """Compute relative strength of each sector versus SPY. Cache for four hours."""
    cache_key = "sector:strength:v1"
    if redis_client is not None:
        cached = await redis_client.get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass

    spy_payload = await market_data.get_bars("SPY", "1Y", tf="1Day")
    spy = _close_series(spy_payload.get("bars") or [])
    out: dict[str, Any] = {}

    for sector, etf in SECTOR_ETFS.items():
        try:
            payload = await market_data.get_bars(etf, "1Y", tf="1Day")
            s = _close_series(payload.get("bars") or [])
        except Exception:
            continue
        if len(s) < 60 or len(spy) < 60:
            continue
        rs_20 = _relative_return(s, spy, 20)
        rs_60 = _relative_return(s, spy, 60)
        rs_120 = _relative_return(s, spy, 120)
        out[sector] = {
            "etf": etf,
            "rs_20": round(rs_20, 4),
            "rs_60": round(rs_60, 4),
            "rs_120": round(rs_120, 4),
            "rs_combined": round(rs_20 * 0.5 + rs_60 * 0.3 + rs_120 * 0.2, 4),
        }

    ranked = sorted(out.items(), key=lambda kv: float(kv[1]["rs_combined"]), reverse=True)
    leading = [k for k, _ in ranked[:3]]
    lagging = [k for k, _ in ranked[-3:]]
    result = {
        "sectors": out,
        "leading": leading,
        "lagging": lagging,
        "computed_at": datetime.utcnow().isoformat(),
    }
    if redis_client is not None:
        await redis_client.setex(cache_key, 14400, json.dumps(result))
    return result


def sector_modifier_for_ticker(ticker: str, sector_data: dict[str, Any]) -> float:
    sector = TICKER_SECTOR.get(ticker.upper())
    if not sector:
        return 1.0
    if sector in (sector_data.get("leading") or []):
        return 1.15
    if sector in (sector_data.get("lagging") or []):
        return 0.85
    return 1.0


def sector_position_for_ticker(ticker: str, sector_data: dict[str, Any]) -> str:
    mult = sector_modifier_for_ticker(ticker, sector_data)
    if mult > 1.0:
        return "leading"
    if mult < 1.0:
        return "lagging"
    return "neutral"
