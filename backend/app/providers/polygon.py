from __future__ import annotations

from datetime import datetime
from typing import Any
import httpx

from app.config import get_settings
from app.providers.base import MarketDataProvider


settings = get_settings()


class PolygonProvider(MarketDataProvider):
    name = "polygon"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    @staticmethod
    def configured() -> bool:
        return bool(settings.polygon_api_key)

    async def quote(self, symbol: str) -> dict[str, Any] | None:
        if not self.configured():
            return None
        resp = await self.client.get(
            f"https://api.polygon.io/v2/aggs/ticker/{symbol.upper()}/prev",
            params={"adjusted": "true", "apiKey": settings.polygon_api_key},
        )
        resp.raise_for_status()
        item = ((resp.json().get("results") or [])[:1] or [{}])[0]
        price = float(item.get("c") or 0.0)
        if price <= 0:
            return None
        return {"ticker": symbol.upper(), "price": price, "timestamp": datetime.utcnow()}

    async def candles(self, symbol: str, start: datetime, end: datetime, timeframe: str) -> list[dict[str, Any]]:
        if not self.configured():
            return []
        mult, span = (1, "day") if timeframe == "1Day" else (1, "hour")
        if timeframe == "1Min":
            mult, span = 5, "minute"
        elif timeframe == "5Min":
            mult, span = 15, "minute"
        url = f"https://api.polygon.io/v2/aggs/ticker/{symbol.upper()}/range/{mult}/{span}/{start.date().isoformat()}/{end.date().isoformat()}"
        resp = await self.client.get(url, params={"adjusted": "true", "sort": "asc", "apiKey": settings.polygon_api_key})
        resp.raise_for_status()
        out: list[dict[str, Any]] = []
        for item in (resp.json().get("results") or []):
            c = float(item.get("c") or 0.0)
            if c <= 0:
                continue
            out.append(
                {
                    "price": c,
                    "volume": float(item.get("v") or 0.0),
                    "open_price": float(item.get("o") or c),
                    "high_price": float(item.get("h") or c),
                    "low_price": float(item.get("l") or c),
                    "timestamp": datetime.utcfromtimestamp(int(item.get("t", 0)) / 1000.0),
                }
            )
        return out
