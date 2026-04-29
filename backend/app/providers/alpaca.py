from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
import httpx

from app.config import get_settings
from app.providers.base import MarketDataProvider


settings = get_settings()
logger = logging.getLogger(__name__)


class AlpacaProvider(MarketDataProvider):
    name = "alpaca"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client
        self.redis = None

    def bind_redis(self, redis: Any) -> None:
        self.redis = redis

    @staticmethod
    def _headers() -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": settings.alpaca_api_key,
            "APCA-API-SECRET-KEY": settings.alpaca_secret_key,
        }

    @staticmethod
    def configured() -> bool:
        return bool(settings.alpaca_api_key and settings.alpaca_secret_key)

    @staticmethod
    def _log_rate_limit(resp: httpx.Response) -> None:
        try:
            remaining = int(resp.headers.get("X-Ratelimit-Remaining", "200"))
        except ValueError:
            return
        if remaining < 10:
            logger.error("Alpaca rate limit critical: %s/200 remaining", remaining)
        elif remaining < 50:
            logger.warning("Alpaca rate limit low: %s/200 remaining", remaining)

    @staticmethod
    def _deserialize_quote(raw: str) -> dict[str, Any] | None:
        try:
            payload = json.loads(raw)
            ts = payload.get("timestamp")
            if isinstance(ts, str):
                payload["timestamp"] = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return payload
        except Exception:
            return None

    @staticmethod
    def _snapshot_to_quote(sym: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        latest_trade = payload.get("latestTrade") or {}
        latest_quote = payload.get("latestQuote") or {}
        minute_bar = payload.get("minuteBar") or {}
        daily_bar = payload.get("dailyBar") or {}
        prev_daily_bar = payload.get("prevDailyBar") or {}

        px = float(latest_trade.get("p") or 0.0)
        if px <= 0:
            ask = float(latest_quote.get("ap") or 0.0)
            bid = float(latest_quote.get("bp") or 0.0)
            px = ((ask + bid) / 2.0) if ask > 0 and bid > 0 else (ask or bid)
        if px <= 0:
            return None

        open_px = float(daily_bar.get("o") or minute_bar.get("o") or px)
        high_px = float(daily_bar.get("h") or minute_bar.get("h") or px)
        low_px = float(daily_bar.get("l") or minute_bar.get("l") or px)
        volume = float(daily_bar.get("v") or minute_bar.get("v") or 0.0)
        prev_close = float(prev_daily_bar.get("c") or 0.0)
        change_percent = ((px - prev_close) / prev_close * 100.0) if prev_close > 0 else 0.0
        ts_raw = latest_trade.get("t") or latest_quote.get("t")
        ts = datetime.now(timezone.utc)
        if ts_raw:
            try:
                ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
            except Exception:
                ts = datetime.now(timezone.utc)

        return {
            "ticker": sym,
            "price": px,
            "open_price": open_px,
            "high_price": high_px,
            "low_price": low_px,
            "volume": volume,
            "change_percent": change_percent,
            "previous_close": prev_close,
            "timestamp": ts,
            "source": "alpaca",
        }

    async def _get_cached_quote(self, sym: str) -> dict[str, Any] | None:
        if self.redis is None:
            return None
        cached = await self.redis.get(f"alpaca:snapshot:{sym}")
        return self._deserialize_quote(cached) if cached else None

    async def _set_cached_quote(self, sym: str, result: dict[str, Any]) -> None:
        if self.redis is None:
            return
        await self.redis.setex(f"alpaca:snapshot:{sym}", 10, json.dumps(result, default=str))

    async def quote(self, symbol: str) -> dict[str, Any] | None:
        if not self.configured():
            return None
        sym = symbol.upper()
        cached = await self._get_cached_quote(sym)
        if cached:
            return cached

        resp = await self.client.get(
            f"{settings.alpaca_data_url.rstrip('/')}/v2/stocks/{sym}/snapshot",
            params={"feed": settings.alpaca_data_feed or "iex"},
            headers=self._headers(),
        )
        self._log_rate_limit(resp)
        resp.raise_for_status()
        result = self._snapshot_to_quote(sym, resp.json() or {})
        if result is None:
            return None
        await self._set_cached_quote(sym, result)
        return result

    async def candles(self, symbol: str, start: datetime, end: datetime, timeframe: str) -> list[dict[str, Any]]:
        if not self.configured():
            return []
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        sym = symbol.upper()
        url = f"{settings.alpaca_data_url.rstrip('/')}/v2/stocks/{sym}/bars"
        params: dict[str, Any] = {
            "timeframe": timeframe,
            "start": start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "feed": settings.alpaca_data_feed or "iex",
            "limit": 10000,
            "adjustment": "split",
            "sort": "asc",
        }
        bars: list[dict[str, Any]] = []
        next_page_token: str | None = None
        while True:
            call_params = dict(params)
            if next_page_token:
                call_params["page_token"] = next_page_token
            resp = await self.client.get(url, params=call_params, headers=self._headers())
            self._log_rate_limit(resp)
            resp.raise_for_status()
            payload = resp.json() or {}
            bars.extend(payload.get("bars") or [])
            next_page_token = payload.get("next_page_token")
            if not next_page_token:
                break

        out: list[dict[str, Any]] = []
        for bar in bars:
            close = float(bar.get("c") or 0.0)
            if close <= 0:
                continue
            ts = datetime.fromisoformat(str(bar.get("t")).replace("Z", "+00:00"))
            out.append(
                {
                    "price": close,
                    "volume": float(bar.get("v") or 0.0),
                    "open_price": float(bar.get("o") or close),
                    "high_price": float(bar.get("h") or close),
                    "low_price": float(bar.get("l") or close),
                    "timestamp": ts,
                    "source": "alpaca",
                }
            )
        return out

    async def snapshots_batch(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        if not self.configured() or not symbols:
            return {}
        normalized = list(dict.fromkeys(s.upper().strip() for s in symbols if s.strip()))[:100]
        out: dict[str, dict[str, Any]] = {}
        missing: list[str] = []
        for sym in normalized:
            cached = await self._get_cached_quote(sym)
            if cached:
                out[sym] = cached
            else:
                missing.append(sym)
        if not missing:
            return out

        resp = await self.client.get(
            f"{settings.alpaca_data_url.rstrip('/')}/v2/stocks/snapshots",
            params={"symbols": ",".join(missing), "feed": settings.alpaca_data_feed or "iex"},
            headers=self._headers(),
        )
        self._log_rate_limit(resp)
        resp.raise_for_status()
        raw = resp.json() or {}
        for sym, snapshot in raw.items():
            result = self._snapshot_to_quote(str(sym).upper(), snapshot or {})
            if result is None:
                continue
            out[str(sym).upper()] = result
            await self._set_cached_quote(str(sym).upper(), result)
        return out

    async def snapshots(self, symbols: list[str]) -> dict[str, Any]:
        return await self.snapshots_batch(symbols)
