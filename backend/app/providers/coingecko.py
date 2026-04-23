from __future__ import annotations

from datetime import datetime
from typing import Any
import httpx

from app.providers.base import MarketDataProvider


class CoinGeckoProvider(MarketDataProvider):
    name = "coingecko"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def quote(self, symbol: str) -> dict[str, Any] | None:
        return None

    async def candles(self, symbol: str, start: datetime, end: datetime, timeframe: str) -> list[dict[str, Any]]:
        return []
