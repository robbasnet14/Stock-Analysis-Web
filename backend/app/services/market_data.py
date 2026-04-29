from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any
import httpx
import numpy as np
try:
    from lttb import downsample
except Exception:  # pragma: no cover
    downsample = None

from app.config import get_settings
from app.core import BucketSpec, RedisTokenBucketLimiter
from app.core.provider_router import ProviderRouter
from app.providers import (
    AlpacaProvider,
    BinanceProvider,
    CoinGeckoProvider,
    FinnhubProvider,
    NewsRssProvider,
    PolygonProvider,
    TiingoProvider,
    YFinanceFallbackProvider,
)


logger = logging.getLogger(__name__)

RANGE_CONFIG: dict[str, dict[str, Any]] = {
    "1D": {"lookback_days": 1, "default_tf": "1Min", "max_points": 390},
    "1W": {"lookback_days": 7, "default_tf": "5Min", "max_points": 400},
    "1M": {"lookback_days": 31, "default_tf": "15Min", "max_points": 500},
    "3M": {"lookback_days": 93, "default_tf": "1Hour", "max_points": 500},
    "1Y": {"lookback_days": 365, "default_tf": "1Day", "max_points": 260},
    "ALL": {"lookback_days": 3650, "default_tf": "1Day", "max_points": 500},
}


def normalize_tf(tf: str) -> str:
    mapping = {
        "1min": "1Min",
        "1m": "1Min",
        "1Min": "1Min",
        "5min": "5Min",
        "5m": "5Min",
        "5Min": "5Min",
        "15min": "15Min",
        "15Min": "15Min",
        "30min": "30Min",
        "30Min": "30Min",
        "1h": "1Hour",
        "60min": "1Hour",
        "1hour": "1Hour",
        "1Hour": "1Hour",
        "1d": "1Day",
        "1D": "1Day",
        "1day": "1Day",
        "1Day": "1Day",
        "1w": "1Week",
        "1Week": "1Week",
    }
    if tf not in mapping:
        raise ValueError(f"Unknown timeframe {tf}")
    return mapping[tf]


class MarketDataService:
    """Unified market data entry-point (primary + failover)."""

    def __init__(self) -> None:
        settings = get_settings()
        self.settings = settings
        self.client = httpx.AsyncClient(timeout=15.0)
        self.router = ProviderRouter()
        self.limiter = RedisTokenBucketLimiter(None)
        self.alpaca = AlpacaProvider(self.client)
        self.finnhub = FinnhubProvider(self.client)
        self.tiingo = TiingoProvider(self.client)
        self.polygon = PolygonProvider(self.client)
        self.yf = YFinanceFallbackProvider()
        self.binance = BinanceProvider(self.client)
        self.coingecko = CoinGeckoProvider(self.client)
        self.news_rss = NewsRssProvider(self.client)

        self.router.register(self.alpaca.name, self.alpaca.configured())
        self.router.register(self.finnhub.name, self.finnhub.configured())
        self.router.register(self.tiingo.name, self.tiingo.configured())
        self.router.register(self.polygon.name, self.polygon.configured())
        self.router.register(self.binance.name, True)
        self.router.register(self.coingecko.name, True)
        self.router.register(self.yf.name, True)

    async def close(self) -> None:
        await self.client.aclose()

    def bind_redis(self, redis: Any) -> None:
        self.limiter = RedisTokenBucketLimiter(redis)
        self.alpaca.bind_redis(redis)

    async def _allow(self, provider: str, op: str) -> bool:
        prefix = self.settings.rate_limit_redis_prefix or "ratelimit:"
        key = f"{prefix}{provider}:{op}"
        specs: dict[tuple[str, str], BucketSpec] = {
            ("alpaca", "quote"): BucketSpec(capacity=30, refill_per_sec=10.0),
            ("alpaca", "candles"): BucketSpec(capacity=20, refill_per_sec=5.0),
            ("finnhub", "quote"): BucketSpec(capacity=15, refill_per_sec=1.0),
            ("finnhub", "search"): BucketSpec(capacity=30, refill_per_sec=1.0),
            ("finnhub", "symbols"): BucketSpec(capacity=5, refill_per_sec=0.1),
            ("finnhub", "news"): BucketSpec(capacity=60, refill_per_sec=1.0),
            ("polygon", "quote"): BucketSpec(capacity=5, refill_per_sec=0.2),
            ("polygon", "candles"): BucketSpec(capacity=5, refill_per_sec=0.2),
            ("tiingo", "candles"): BucketSpec(capacity=50, refill_per_sec=0.25),
            ("binance", "quote"): BucketSpec(capacity=120, refill_per_sec=5.0),
            ("binance", "candles"): BucketSpec(capacity=120, refill_per_sec=5.0),
            ("coingecko", "quote"): BucketSpec(capacity=30, refill_per_sec=0.5),
            ("coingecko", "candles"): BucketSpec(capacity=30, refill_per_sec=0.5),
        }
        spec = specs.get((provider, op), BucketSpec(capacity=20, refill_per_sec=1.0))
        return await self.limiter.allow(key, spec)

    @staticmethod
    def _is_crypto_symbol(symbol: str) -> bool:
        s = (symbol or "").upper().strip()
        return (
            s.endswith("USDT")
            or s.endswith("USD")
            or "-" in s
            or s in {"BTC", "ETH", "SOL", "DOGE", "BNB", "XRP"}
        )

    async def get_quote(self, symbol: str) -> dict[str, Any]:
        symbol = (symbol or "").upper().strip()
        errors: list[str] = []
        provider_order: list[tuple[str, Any, int]] = []
        if self._is_crypto_symbol(symbol):
            provider_order.extend(
                [
                    ("binance", self.binance, 10),
                    ("coingecko", self.coingecko, 30),
                ]
            )
        provider_order.extend(
            [
                ("alpaca", self.alpaca, 15),
                ("finnhub", self.finnhub, 60),
                ("polygon", self.polygon, 120),
            ]
        )
        if not self.settings.provider_failover_enabled and provider_order:
            provider_order = provider_order[:1]
        for name, provider, cooldown in provider_order:
            if not self.router.can_try(provider.name):
                continue
            if not await self._allow(provider.name, "quote"):
                self.router.record_failure(provider.name, "rate limit guard", cooldown_s=5, trip_breaker=False)
                errors.append(f"{name}: local rate guard")
                continue
            try:
                row = await provider.quote(symbol)
                if row:
                    self.router.record_success(provider.name)
                    return row
                self.router.record_failure(provider.name, "empty quote", cooldown_s=10, trip_breaker=False)
                errors.append(f"{name}: empty")
            except Exception as exc:
                self.router.record_failure(provider.name, str(exc), cooldown_s=cooldown)
                errors.append(f"{name}: {exc}")
        raise RuntimeError(f"no quote for {symbol}: {' | '.join(errors) or 'no providers'}")

    async def get_quotes(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        normalized = list(dict.fromkeys((s or "").upper().strip() for s in symbols if (s or "").strip()))
        if not normalized:
            return {}
        out: dict[str, dict[str, Any]] = {}
        equity_symbols = [s for s in normalized if not self._is_crypto_symbol(s)]
        if equity_symbols and self.alpaca.configured() and self.router.can_try(self.alpaca.name):
            if await self._allow(self.alpaca.name, "quote"):
                try:
                    out.update(await self.alpaca.snapshots_batch(equity_symbols))
                    self.router.record_success(self.alpaca.name)
                except Exception as exc:
                    self.router.record_failure(self.alpaca.name, str(exc), cooldown_s=30)
            else:
                self.router.record_failure(self.alpaca.name, "rate limit guard", cooldown_s=5, trip_breaker=False)

        for symbol in normalized:
            if symbol in out:
                continue
            try:
                out[symbol] = await self.get_quote(symbol)
            except Exception:
                logger.exception("quote batch fallback failed: ticker=%s", symbol)
        return out

    async def get_candles(self, symbol: str, span: str, tf: str | None = None) -> list[dict[str, Any]]:
        # Legacy compatibility: return simple [{price,...,timestamp}] rows.
        payload = await self.get_bars(symbol=symbol, span=span, tf=tf)
        out: list[dict[str, Any]] = []
        for b in payload.get("bars", []):
            close = float(b.get("close") or 0.0)
            open_px = float(b.get("open") or close)
            high_px = float(b.get("high") or close)
            low_px = float(b.get("low") or close)
            ts = b.get("timestamp")
            if isinstance(ts, str):
                try:
                    ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except Exception:
                    ts_dt = datetime.now(timezone.utc)
            else:
                ts_dt = ts if isinstance(ts, datetime) else datetime.now(timezone.utc)
            out.append(
                {
                    "price": close,
                    "volume": float(b.get("volume") or 0.0),
                    "open_price": open_px,
                    "high_price": high_px,
                    "low_price": low_px,
                    "timestamp": ts_dt,
                }
            )
        return out

    async def get_bars(self, symbol: str, span: str, tf: str | None = None, max_points: int | None = None) -> dict[str, Any]:
        sym = (symbol or "").upper().strip()
        range_key = (span or "1D").upper()
        cfg = RANGE_CONFIG.get(range_key)
        if cfg is None:
            raise ValueError(f"Unknown range {span}")

        if tf:
            tf_norm = normalize_tf(tf)
        else:
            tf_norm = str(cfg["default_tf"])

        now = datetime.now(timezone.utc)
        intraday = tf_norm in ("1Min", "5Min", "15Min", "30Min", "1Hour")
        end = now - timedelta(minutes=16) if intraday else now
        start = end - timedelta(days=int(cfg["lookback_days"]))
        start_s = start.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_s = end.strftime("%Y-%m-%dT%H:%M:%SZ")

        provider_order: list[tuple[Any, int]] = []
        if self._is_crypto_symbol(sym):
            provider_order = [(self.binance, 20), (self.coingecko, 30)]
        elif intraday:
            provider_order = [(self.alpaca, 30), (self.polygon, 120)]
        else:
            provider_order = [(self.tiingo, 45), (self.alpaca, 60), (self.polygon, 120)]

        if not self.settings.provider_failover_enabled and provider_order:
            provider_order = provider_order[:1]

        errors: list[str] = []
        source = "none"
        bars: list[dict[str, Any]] = []

        for provider, cooldown in provider_order:
            if not self.router.can_try(provider.name):
                continue
            if not await self._allow(provider.name, "candles"):
                self.router.record_failure(provider.name, "rate limit guard", cooldown_s=5, trip_breaker=False)
                errors.append(f"{provider.name}: rate guard")
                continue
            try:
                rows = await provider.candles(sym, start, end, tf_norm)
                if not rows:
                    self.router.record_failure(provider.name, "empty candles", cooldown_s=10, trip_breaker=False)
                    errors.append(f"{provider.name}: empty")
                    continue
                self.router.record_success(provider.name)
                bars = self._canonicalize_bars(rows)
                source = provider.name
                break
            except Exception as exc:
                self.router.record_failure(provider.name, str(exc), cooldown_s=cooldown)
                errors.append(f"{provider.name}: {exc}")

        bars = self._downsample_bars(bars, int(max_points if max_points is not None else cfg["max_points"]))
        logger.info(
            "bars request: ticker=%s tf=%s range=%s start=%s end=%s provider=%s count=%s source=%s errors=%s",
            sym,
            tf_norm,
            range_key,
            start_s,
            end_s,
            source,
            len(bars),
            source,
            " | ".join(errors[-3:]) if errors else "",
        )
        return {
            "ticker": sym,
            "tf": tf_norm,
            "range": range_key,
            "source": source,
            "start": start_s,
            "end": end_s,
            "bars": bars,
            "data": bars,
        }

    async def search(self, q: str) -> list[dict[str, Any]]:
        if self.router.can_try(self.finnhub.name):
            if not await self._allow(self.finnhub.name, "search"):
                self.router.record_failure(self.finnhub.name, "rate limit guard", cooldown_s=5, trip_breaker=False)
                return []
            try:
                out = await self.finnhub.search(q)
                if out:
                    self.router.record_success(self.finnhub.name)
                    return out
            except Exception as exc:
                self.router.record_failure(self.finnhub.name, str(exc), cooldown_s=60)
        return []

    async def symbol_master(self) -> list[dict[str, Any]]:
        if self.router.can_try(self.finnhub.name):
            if not await self._allow(self.finnhub.name, "symbols"):
                self.router.record_failure(self.finnhub.name, "rate limit guard", cooldown_s=5, trip_breaker=False)
                return []
            try:
                out = await self.finnhub.symbols()
                if out:
                    self.router.record_success(self.finnhub.name)
                    return out
            except Exception as exc:
                self.router.record_failure(self.finnhub.name, str(exc), cooldown_s=120)
        return []

    async def ticker_news(self, symbol: str) -> list[dict[str, Any]]:
        now = datetime.utcnow()
        from_dt = now - timedelta(days=7)
        if await self._allow(self.finnhub.name, "news"):
            try:
                rows = await self.finnhub.news(symbol, from_dt, now)
            except Exception:
                rows = []
        else:
            rows = []
        try:
            if rows:
                self.router.record_success(self.finnhub.name)
        except Exception:
            pass
        if rows:
            return rows
        rss = await self.news_rss.yahoo(symbol)
        return rss

    def provider_health(self) -> dict[str, dict[str, Any]]:
        return self.router.snapshot()

    @staticmethod
    def _canonicalize_bars(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for row in rows:
            close = float(row.get("close") or row.get("price") or 0.0)
            if close <= 0:
                continue
            open_px = float(row.get("open") or row.get("open_price") or close)
            high_px = float(row.get("high") or row.get("high_price") or close)
            low_px = float(row.get("low") or row.get("low_price") or close)
            vol = float(row.get("volume") or 0.0)
            ts = row.get("timestamp")
            if isinstance(ts, str):
                try:
                    ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except Exception:
                    ts_dt = datetime.now(timezone.utc)
            elif isinstance(ts, datetime):
                ts_dt = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
            else:
                ts_dt = datetime.now(timezone.utc)
            out.append(
                {
                    "timestamp": ts_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "open": open_px,
                    "high": high_px,
                    "low": low_px,
                    "close": close,
                    "volume": vol,
                }
            )
        out.sort(key=lambda x: x["timestamp"])
        return out

    @staticmethod
    def _downsample_bars(bars: list[dict[str, Any]], max_points: int) -> list[dict[str, Any]]:
        if len(bars) <= max_points or max_points <= 2:
            return bars
        if downsample is None:
            return bars[:max_points]
        try:
            arr = np.array(
                [
                    [int(datetime.fromisoformat(b["timestamp"].replace("Z", "+00:00")).timestamp()), float(b["close"])]
                    for b in bars
                ],
                dtype=float,
            )
            ds = downsample(arr, n_out=max_points)
            exact = {
                int(datetime.fromisoformat(b["timestamp"].replace("Z", "+00:00")).timestamp()): b for b in bars
            }
            out: list[dict[str, Any]] = []
            for ts_num, close_val in ds:
                sec = int(ts_num)
                if sec in exact:
                    out.append(exact[sec])
                    continue
                ts = datetime.fromtimestamp(sec, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                close = float(close_val)
                out.append(
                    {
                        "timestamp": ts,
                        "open": close,
                        "high": close,
                        "low": close,
                        "close": close,
                        "volume": 0.0,
                    }
                )
            out.sort(key=lambda x: x["timestamp"])
            return out
        except Exception:
            return bars[:max_points]
