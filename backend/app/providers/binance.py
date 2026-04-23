from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import httpx

from app.config import get_settings
from app.providers.base import MarketDataProvider


settings = get_settings()


class BinanceProvider(MarketDataProvider):
    name = "binance"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    @staticmethod
    def _to_pair(symbol: str) -> str:
        s = symbol.upper().strip()
        mapping = {
            "BTC-USD": "BTCUSDT",
            "ETH-USD": "ETHUSDT",
            "SOL-USD": "SOLUSDT",
        }
        if s in mapping:
            return mapping[s]
        if s.endswith("-USD"):
            return f"{s.split('-')[0]}USDT"
        return s.replace("-", "")

    async def _get_with_us_fallback(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        primary = (settings.binance_rest_url or "https://api.binance.com").rstrip("/")
        resp = await self.client.get(f"{primary}{path}", params=params)
        if resp.status_code in (403, 451) and settings.binance_us_fallback:
            fallback = "https://api.binance.us"
            resp = await self.client.get(f"{fallback}{path}", params=params)
        resp.raise_for_status()
        return resp.json() or {}

    async def quote(self, symbol: str) -> dict[str, Any] | None:
        pair = self._to_pair(symbol)
        data = await self._get_with_us_fallback("/api/v3/ticker/24hr", {"symbol": pair})
        price = float(data.get("lastPrice") or 0.0)
        if price <= 0:
            return None
        open_price = float(data.get("openPrice") or price)
        high_price = float(data.get("highPrice") or price)
        low_price = float(data.get("lowPrice") or price)
        volume = float(data.get("volume") or 0.0)
        change_percent = float(data.get("priceChangePercent") or 0.0)
        return {
            "ticker": symbol.upper(),
            "price": price,
            "open_price": open_price,
            "high_price": high_price,
            "low_price": low_price,
            "volume": volume,
            "change_percent": change_percent,
            "timestamp": datetime.now(timezone.utc),
            "source": "binance",
        }

    async def candles(self, symbol: str, start: datetime, end: datetime, timeframe: str) -> list[dict[str, Any]]:
        tf_map = {"1Min": "1m", "5Min": "5m", "15Min": "15m", "1Hour": "1h", "1Day": "1d", "1Week": "1w"}
        interval = tf_map.get(timeframe, "1h")
        pair = self._to_pair(symbol)
        data = await self._get_with_us_fallback("/api/v3/klines", {"symbol": pair, "interval": interval, "limit": 1000})
        rows: list[dict[str, Any]] = []
        for r in (data or []):
            close = float(r[4])
            rows.append(
                {
                    "price": close,
                    "volume": float(r[5]),
                    "open_price": float(r[1]),
                    "high_price": float(r[2]),
                    "low_price": float(r[3]),
                    "timestamp": datetime.fromtimestamp(int(r[0]) / 1000.0, tz=timezone.utc),
                    "source": "binance",
                }
            )
        return rows
