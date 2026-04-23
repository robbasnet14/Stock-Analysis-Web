from __future__ import annotations

from datetime import datetime
from typing import Any
import httpx

from app.config import get_settings
from app.providers.base import MarketDataProvider


settings = get_settings()


class TiingoProvider(MarketDataProvider):
    name = "tiingo"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    @staticmethod
    def configured() -> bool:
        return bool(settings.tiingo_api_key)

    async def quote(self, symbol: str) -> dict[str, Any] | None:
        return None

    async def candles(self, symbol: str, start: datetime, end: datetime, timeframe: str) -> list[dict[str, Any]]:
        if not self.configured():
            return []
        resp = await self.client.get(
            f"https://api.tiingo.com/tiingo/daily/{symbol.upper()}/prices",
            params={
                "startDate": start.date().isoformat(),
                "endDate": end.date().isoformat(),
                "token": settings.tiingo_api_key,
                "resampleFreq": "daily",
            },
        )
        resp.raise_for_status()
        rows: list[dict[str, Any]] = []
        for item in (resp.json() or []):
            close = float(item.get("adjClose") or item.get("close") or 0.0)
            if close <= 0:
                continue
            dt = datetime.fromisoformat(str(item.get("date")).replace("Z", "+00:00")).replace(tzinfo=None)
            rows.append(
                {
                    "price": close,
                    "volume": float(item.get("adjVolume") or item.get("volume") or 0.0),
                    "open_price": float(item.get("adjOpen") or item.get("open") or close),
                    "high_price": float(item.get("adjHigh") or item.get("high") or close),
                    "low_price": float(item.get("adjLow") or item.get("low") or close),
                    "timestamp": dt,
                }
            )
        return rows
