from __future__ import annotations

from datetime import datetime
from typing import Any

from app.providers.base import MarketDataProvider


class YFinanceFallbackProvider(MarketDataProvider):
    name = "yfinance_fallback"

    async def quote(self, symbol: str) -> dict[str, Any] | None:
        return None

    async def candles(self, symbol: str, start: datetime, end: datetime, timeframe: str) -> list[dict[str, Any]]:
        return []
