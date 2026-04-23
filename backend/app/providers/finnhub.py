from __future__ import annotations

from datetime import datetime
from typing import Any
import httpx

from app.config import get_settings
from app.providers.base import MarketDataProvider


settings = get_settings()


class FinnhubProvider(MarketDataProvider):
    name = "finnhub"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    @staticmethod
    def configured() -> bool:
        return bool(settings.finnhub_api_key)

    async def quote(self, symbol: str) -> dict[str, Any] | None:
        if not self.configured():
            return None
        resp = await self.client.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": symbol.upper(), "token": settings.finnhub_api_key},
        )
        resp.raise_for_status()
        data = resp.json()
        price = float(data.get("c") or 0.0)
        if price <= 0:
            return None
        return {
            "ticker": symbol.upper(),
            "price": price,
            "change_percent": float(data.get("dp") or 0.0),
            "open_price": float(data.get("o") or price),
            "high_price": float(data.get("h") or price),
            "low_price": float(data.get("l") or price),
            "timestamp": datetime.utcnow(),
        }

    async def candles(self, symbol: str, start: datetime, end: datetime, timeframe: str) -> list[dict[str, Any]]:
        return []

    async def search(self, query: str) -> list[dict[str, Any]]:
        if not self.configured():
            return []
        resp = await self.client.get("https://finnhub.io/api/v1/search", params={"q": query, "token": settings.finnhub_api_key})
        resp.raise_for_status()
        out: list[dict[str, Any]] = []
        for item in (resp.json().get("result") or [])[:25]:
            symbol = str(item.get("symbol") or "").upper()
            if not symbol:
                continue
            out.append({
                "symbol": symbol,
                "display_symbol": str(item.get("displaySymbol") or symbol).upper(),
                "description": str(item.get("description") or ""),
                "type": str(item.get("type") or ""),
            })
        return out

    async def symbols(self) -> list[dict[str, Any]]:
        if not self.configured():
            return []
        resp = await self.client.get(
            "https://finnhub.io/api/v1/stock/symbol",
            params={"exchange": "US", "token": settings.finnhub_api_key},
            follow_redirects=True,
        )
        resp.raise_for_status()
        return list(resp.json() or [])

    async def news(self, symbol: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        if not self.configured():
            return []
        resp = await self.client.get(
            "https://finnhub.io/api/v1/company-news",
            params={
                "symbol": symbol.upper(),
                "from": start.date().isoformat(),
                "to": end.date().isoformat(),
                "token": settings.finnhub_api_key,
            },
        )
        resp.raise_for_status()
        return list(resp.json() or [])
