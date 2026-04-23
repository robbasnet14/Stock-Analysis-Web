from datetime import datetime, timedelta
import httpx
import numpy as np
import pandas as pd
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.models.news import NewsArticle
from app.models.stock import StockPrice
from app.models.symbol import SymbolMaster
from app.models.technical_indicator import TechnicalIndicator
from app.utils.ta import (
    compute_adx,
    compute_bollinger,
    compute_macd,
    compute_obv,
    compute_roc,
    compute_rsi,
    compute_vwap,
)


settings = get_settings()


class StockService:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(timeout=15.0)
        self._rate_limit_cooldown_seconds: dict[str, int] = {
            "alpaca_data": 15,
            "finnhub": 60,
            "polygon": 120,
            "tiingo": 120,
        }
        self.provider_health: dict[str, dict] = {
            "alpaca_data": self._new_provider_health(bool(settings.alpaca_api_key and settings.alpaca_secret_key)),
            "finnhub": self._new_provider_health(bool(settings.finnhub_api_key)),
            "polygon": self._new_provider_health(bool(settings.polygon_api_key)),
            "tiingo": self._new_provider_health(bool(settings.tiingo_api_key)),
        }

    @staticmethod
    def _new_provider_health(configured: bool) -> dict:
        return {
            "configured": configured,
            "last_ok": None,
            "last_error": None,
            "last_latency_ms": None,
            "last_checked": None,
            "successes": 0,
            "failures": 0,
            "consecutive_failures": 0,
            "breaker_until": None,
        }

    def _record_provider(self, provider: str, ok: bool, *, latency_ms: float | None = None, error: str | None = None) -> None:
        row = self.provider_health.setdefault(provider, self._new_provider_health(False))
        row["last_checked"] = datetime.utcnow().isoformat()
        if latency_ms is not None:
            row["last_latency_ms"] = round(float(latency_ms), 2)
        if ok:
            row["successes"] = int(row.get("successes", 0)) + 1
            row["last_ok"] = datetime.utcnow().isoformat()
            row["last_error"] = None
            row["consecutive_failures"] = 0
            row["breaker_until"] = None
        else:
            row["failures"] = int(row.get("failures", 0)) + 1
            row["consecutive_failures"] = int(row.get("consecutive_failures", 0)) + 1
            row["last_error"] = str(error or "unknown error")[:400]

    def get_provider_health(self) -> dict[str, dict]:
        return {k: dict(v) for k, v in self.provider_health.items()}

    @staticmethod
    def _parse_iso_dt(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return None

    def _provider_can_attempt(self, provider: str, errors: list[str]) -> bool:
        row = self.provider_health.setdefault(provider, self._new_provider_health(False))
        breaker_until = self._parse_iso_dt(str(row.get("breaker_until") or ""))
        if breaker_until is None:
            return True
        now = datetime.utcnow()
        if now >= breaker_until:
            row["breaker_until"] = None
            return True
        wait_s = int((breaker_until - now).total_seconds())
        errors.append(f"{provider}: cooling down ({wait_s}s)")
        return False

    def _trip_breaker(self, provider: str, cooldown_seconds: int, reason: str) -> None:
        row = self.provider_health.setdefault(provider, self._new_provider_health(False))
        until = datetime.utcnow() + timedelta(seconds=max(1, int(cooldown_seconds)))
        row["breaker_until"] = until.isoformat()
        row["last_error"] = f"{reason} [cooldown {cooldown_seconds}s]"[:400]

    def _provider_failure_backoff(self, provider: str, status_code: int | None, error_text: str) -> int:
        text = (error_text or "").lower()
        base = int(self._rate_limit_cooldown_seconds.get(provider, 30))
        if status_code == 429 or "rate limit" in text or "too many" in text or "credit" in text or "throttle" in text:
            return max(base, base * 2)
        if status_code in {401, 403}:
            return max(base, 300)
        row = self.provider_health.get(provider) or {}
        consec = int(row.get("consecutive_failures", 0))
        if consec >= 3:
            return min(300, 10 * (2 ** min(consec - 3, 4)))
        return 0

    def _record_provider_failure(self, provider: str, started: datetime, exc: Exception | str, *, status_code: int | None = None) -> None:
        err = str(exc)
        latency_ms = (datetime.utcnow() - started).total_seconds() * 1000.0
        self._record_provider(provider, False, latency_ms=latency_ms, error=err)
        cooldown = self._provider_failure_backoff(provider, status_code, err)
        if cooldown > 0:
            self._trip_breaker(provider, cooldown, err)

    async def close(self) -> None:
        await self.client.aclose()

    @staticmethod
    def _alpaca_data_ready() -> bool:
        return bool(settings.alpaca_api_key and settings.alpaca_secret_key)

    @staticmethod
    def _alpaca_headers() -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": settings.alpaca_api_key,
            "APCA-API-SECRET-KEY": settings.alpaca_secret_key,
        }

    async def fetch_quote(self, ticker: str) -> dict:
        ticker = ticker.upper()
        errors: list[str] = []
        if self._alpaca_data_ready() and self._provider_can_attempt("alpaca_data", errors):
            started = datetime.utcnow()
            try:
                url = f"{settings.alpaca_data_url.rstrip('/')}/v2/stocks/quotes/latest"
                resp = await self.client.get(
                    url,
                    params={"symbols": ticker, "feed": "iex"},
                    headers=self._alpaca_headers(),
                )
                resp.raise_for_status()
                data = resp.json()
                quote = (data.get("quotes") or {}).get(ticker) or {}
                ask = float(quote.get("ap") or 0.0)
                bid = float(quote.get("bp") or 0.0)
                price = ask if ask > 0 else bid
                if price > 0 and bid > 0 and ask > 0:
                    price = (bid + ask) / 2.0
                if price > 0:
                    day = await self._fetch_alpaca_latest_day_bar(ticker)
                    open_price = float(day.get("o") or price)
                    high_price = float(day.get("h") or max(price, open_price))
                    low_price = float(day.get("l") or min(price, open_price))
                    volume = float(day.get("v") or 0.0)
                    prev_close = float(day.get("c") or open_price or price)
                    change_percent = ((price - prev_close) / prev_close * 100.0) if prev_close else 0.0
                    self._record_provider("alpaca_data", True, latency_ms=(datetime.utcnow() - started).total_seconds() * 1000.0)
                    return {
                        "ticker": ticker,
                        "price": price,
                        "change_percent": change_percent,
                        "volume": volume,
                        "open_price": open_price,
                        "high_price": high_price,
                        "low_price": low_price,
                        "timestamp": datetime.utcnow(),
                    }
                errors.append("alpaca empty quote")
                self._record_provider_failure("alpaca_data", started, "empty quote")
            except httpx.HTTPStatusError as exc:
                errors.append(f"alpaca: {exc}")
                self._record_provider_failure("alpaca_data", started, exc, status_code=exc.response.status_code)
            except Exception as exc:
                errors.append(f"alpaca: {exc}")
                self._record_provider_failure("alpaca_data", started, exc)

        if settings.finnhub_api_key and self._provider_can_attempt("finnhub", errors):
            started = datetime.utcnow()
            try:
                url = "https://finnhub.io/api/v1/quote"
                resp = await self.client.get(url, params={"symbol": ticker, "token": settings.finnhub_api_key})
                resp.raise_for_status()
                data = resp.json()
                if data.get("c"):
                    volume = await self._fetch_latest_volume(ticker)
                    self._record_provider("finnhub", True, latency_ms=(datetime.utcnow() - started).total_seconds() * 1000.0)
                    return {
                        "ticker": ticker,
                        "price": float(data.get("c", 0.0)),
                        "change_percent": float(data.get("dp", 0.0)),
                        "volume": float(volume),
                        "open_price": float(data.get("o", data.get("c", 0.0))),
                        "high_price": float(data.get("h", data.get("c", 0.0))),
                        "low_price": float(data.get("l", data.get("c", 0.0))),
                        "timestamp": datetime.utcnow(),
                    }
                errors.append("finnhub empty quote")
                self._record_provider_failure("finnhub", started, "empty quote")
            except httpx.HTTPStatusError as exc:
                errors.append(f"finnhub: {exc}")
                self._record_provider_failure("finnhub", started, exc, status_code=exc.response.status_code)
            except Exception as exc:
                errors.append(f"finnhub: {exc}")
                self._record_provider_failure("finnhub", started, exc)

        if settings.polygon_api_key and self._provider_can_attempt("polygon", errors):
            started = datetime.utcnow()
            try:
                url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev"
                resp = await self.client.get(url, params={"adjusted": "true", "apiKey": settings.polygon_api_key})
                resp.raise_for_status()
                results = resp.json().get("results") or []
                item = results[0] if results else {}
                price = float(item.get("c") or 0.0)
                if price > 0:
                    open_price = float(item.get("o") or price)
                    prev_close = open_price
                    change_percent = ((price - prev_close) / prev_close * 100.0) if prev_close else 0.0
                    self._record_provider("polygon", True, latency_ms=(datetime.utcnow() - started).total_seconds() * 1000.0)
                    return {
                        "ticker": ticker,
                        "price": price,
                        "change_percent": change_percent,
                        "volume": float(item.get("v") or 0.0),
                        "open_price": open_price,
                        "high_price": float(item.get("h") or price),
                        "low_price": float(item.get("l") or price),
                        "timestamp": datetime.utcnow(),
                    }
                errors.append("polygon empty quote")
                self._record_provider_failure("polygon", started, "empty quote")
            except httpx.HTTPStatusError as exc:
                errors.append(f"polygon: {exc}")
                self._record_provider_failure("polygon", started, exc, status_code=exc.response.status_code)
            except Exception as exc:
                errors.append(f"polygon: {exc}")
                self._record_provider_failure("polygon", started, exc)

        raise RuntimeError(f"No live quote returned for {ticker}. Sources: {' | '.join(errors) or 'no provider configured'}")

    async def _fetch_latest_volume(self, ticker: str) -> float:
        if self._alpaca_data_ready():
            bar = await self._fetch_alpaca_latest_minute_bar(ticker)
            if bar:
                return float(bar.get("v") or 0.0)
        # Intentionally avoid Finnhub candle endpoint (premium-gated in many plans).
        return 0.0

    async def _fetch_alpaca_latest_minute_bar(self, ticker: str) -> dict:
        if not self._alpaca_data_ready():
            return {}
        end_dt = datetime.utcnow() - timedelta(minutes=15)
        start_dt = end_dt - timedelta(minutes=45)
        url = f"{settings.alpaca_data_url.rstrip('/')}/v2/stocks/bars"
        try:
            resp = await self.client.get(
                url,
                params={
                    "symbols": ticker.upper(),
                    "timeframe": "1Min",
                    "start": start_dt.isoformat() + "Z",
                    "end": end_dt.isoformat() + "Z",
                    "feed": "iex",
                    "sort": "desc",
                    "limit": 1,
                },
                headers=self._alpaca_headers(),
            )
            resp.raise_for_status()
            bars = (resp.json().get("bars") or {}).get(ticker.upper()) or []
            return bars[0] if bars else {}
        except Exception:
            return {}

    async def _fetch_alpaca_latest_day_bar(self, ticker: str) -> dict:
        if not self._alpaca_data_ready():
            return {}
        end_dt = datetime.utcnow() - timedelta(minutes=15)
        start_dt = end_dt - timedelta(days=7)
        url = f"{settings.alpaca_data_url.rstrip('/')}/v2/stocks/bars"
        try:
            resp = await self.client.get(
                url,
                params={
                    "symbols": ticker.upper(),
                    "timeframe": "1Day",
                    "start": start_dt.date().isoformat(),
                    "end": end_dt.date().isoformat(),
                    "feed": "iex",
                    "sort": "desc",
                    "limit": 1,
                },
                headers=self._alpaca_headers(),
            )
            resp.raise_for_status()
            bars = (resp.json().get("bars") or {}).get(ticker.upper()) or []
            return bars[0] if bars else {}
        except Exception:
            return {}

    def _span_cfg(self, span: str) -> dict:
        span_key = span.upper()
        if span_key == "1D":
            return {"span": span_key, "lookback": timedelta(days=1), "alpaca": "1Min", "polygon_mult": 5, "polygon_span": "minute"}
        if span_key == "1W":
            return {"span": span_key, "lookback": timedelta(days=7), "alpaca": "5Min", "polygon_mult": 15, "polygon_span": "minute"}
        if span_key == "1M":
            return {"span": span_key, "lookback": timedelta(days=31), "alpaca": "1Hour", "polygon_mult": 1, "polygon_span": "hour"}
        if span_key == "1Y":
            return {"span": span_key, "lookback": timedelta(days=366), "alpaca": "1Day", "polygon_mult": 1, "polygon_span": "day", "tiingo_daily": True}
        if span_key == "ALL":
            return {"span": span_key, "lookback": timedelta(days=3650), "alpaca": "1Day", "polygon_mult": 1, "polygon_span": "day", "tiingo_daily": True}
        raise ValueError("range must be one of 1D, 1W, 1M, 1Y, ALL")

    @staticmethod
    def _normalize_candle_rows(rows: list[dict]) -> list[dict]:
        rows.sort(key=lambda x: x["timestamp"])
        prev_close: float | None = None
        out: list[dict] = []
        for row in rows:
            close = float(row["price"])
            if prev_close and prev_close > 0:
                change_percent = ((close - prev_close) / prev_close) * 100.0
            else:
                change_percent = 0.0
            out.append(
                {
                    "price": close,
                    "volume": float(row["volume"]),
                    "change_percent": change_percent,
                    "open_price": float(row["open_price"]),
                    "high_price": float(row["high_price"]),
                    "low_price": float(row["low_price"]),
                    "timestamp": row["timestamp"],
                }
            )
            prev_close = close
        return out

    async def _fetch_candles_alpaca(self, ticker: str, cfg: dict) -> list[dict]:
        errors: list[str] = []
        if not self._alpaca_data_ready() or not self._provider_can_attempt("alpaca_data", errors):
            return []
        started = datetime.utcnow()
        end_dt = datetime.utcnow() - timedelta(minutes=15)
        start_dt = end_dt - cfg["lookback"]
        url = f"{settings.alpaca_data_url.rstrip('/')}/v2/stocks/bars"
        try:
            resp = await self.client.get(
                url,
                params={
                    "symbols": ticker,
                    "timeframe": cfg["alpaca"],
                    "start": start_dt.isoformat() + "Z",
                    "end": end_dt.isoformat() + "Z",
                    "feed": "iex",
                    "adjustment": "all",
                    "sort": "asc",
                    "limit": 10000,
                },
                headers=self._alpaca_headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            bars = (data.get("bars") or {}).get(ticker) or []
            rows: list[dict] = []
            for bar in bars:
                close = float(bar.get("c") or 0.0)
                if close <= 0:
                    continue
                rows.append(
                    {
                        "price": close,
                        "volume": float(bar.get("v") or 0.0),
                        "open_price": float(bar.get("o") or close),
                        "high_price": float(bar.get("h") or close),
                        "low_price": float(bar.get("l") or close),
                        "timestamp": datetime.fromisoformat(str(bar.get("t")).replace("Z", "+00:00")).replace(tzinfo=None),
                    }
                )
            if rows:
                self._record_provider("alpaca_data", True, latency_ms=(datetime.utcnow() - started).total_seconds() * 1000.0)
            else:
                self._record_provider_failure("alpaca_data", started, "empty candles")
            return self._normalize_candle_rows(rows)
        except httpx.HTTPStatusError as exc:
            self._record_provider_failure("alpaca_data", started, exc, status_code=exc.response.status_code)
            return []
        except Exception as exc:
            self._record_provider_failure("alpaca_data", started, exc)
            return []

    async def _fetch_candles_tiingo(self, ticker: str, cfg: dict) -> list[dict]:
        errors: list[str] = []
        if not settings.tiingo_api_key or not self._provider_can_attempt("tiingo", errors):
            return []
        started = datetime.utcnow()
        end_dt = datetime.utcnow()
        start_dt = end_dt - cfg["lookback"]
        url = f"https://api.tiingo.com/tiingo/daily/{ticker}/prices"
        try:
            resp = await self.client.get(
                url,
                params={
                    "startDate": start_dt.date().isoformat(),
                    "endDate": end_dt.date().isoformat(),
                    "token": settings.tiingo_api_key,
                    "resampleFreq": "daily",
                },
            )
            resp.raise_for_status()
            data = resp.json() or []
            rows: list[dict] = []
            for item in data:
                close = float(item.get("adjClose") or item.get("close") or 0.0)
                if close <= 0:
                    continue
                dt = datetime.fromisoformat(str(item.get("date")).replace("Z", "+00:00")).replace(tzinfo=None)
                open_price = float(item.get("adjOpen") or item.get("open") or close)
                high_price = float(item.get("adjHigh") or item.get("high") or close)
                low_price = float(item.get("adjLow") or item.get("low") or close)
                rows.append(
                    {
                        "price": close,
                        "volume": float(item.get("adjVolume") or item.get("volume") or 0.0),
                        "open_price": open_price,
                        "high_price": high_price,
                        "low_price": low_price,
                        "timestamp": dt,
                    }
                )
            if rows:
                self._record_provider("tiingo", True, latency_ms=(datetime.utcnow() - started).total_seconds() * 1000.0)
            else:
                self._record_provider_failure("tiingo", started, "empty candles")
            return self._normalize_candle_rows(rows)
        except httpx.HTTPStatusError as exc:
            self._record_provider_failure("tiingo", started, exc, status_code=exc.response.status_code)
            return []
        except Exception as exc:
            self._record_provider_failure("tiingo", started, exc)
            return []

    async def _fetch_candles_polygon(self, ticker: str, cfg: dict) -> list[dict]:
        errors: list[str] = []
        if not settings.polygon_api_key or not self._provider_can_attempt("polygon", errors):
            return []
        started = datetime.utcnow()
        end_dt = datetime.utcnow()
        start_dt = end_dt - cfg["lookback"]
        url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/{cfg['polygon_mult']}/{cfg['polygon_span']}/{start_dt.date().isoformat()}/{end_dt.date().isoformat()}"
        try:
            resp = await self.client.get(url, params={"adjusted": "true", "sort": "asc", "apiKey": settings.polygon_api_key})
            resp.raise_for_status()
            data = resp.json()
            raw = data.get("results") or []
            rows: list[dict] = []
            for item in raw:
                close = float(item.get("c") or 0.0)
                if close <= 0:
                    continue
                rows.append(
                    {
                        "price": close,
                        "volume": float(item.get("v") or 0.0),
                        "open_price": float(item.get("o") or close),
                        "high_price": float(item.get("h") or close),
                        "low_price": float(item.get("l") or close),
                        "timestamp": datetime.utcfromtimestamp(int(item.get("t", 0)) / 1000.0),
                    }
                )
            if rows:
                self._record_provider("polygon", True, latency_ms=(datetime.utcnow() - started).total_seconds() * 1000.0)
            else:
                self._record_provider_failure("polygon", started, "empty candles")
            return self._normalize_candle_rows(rows)
        except httpx.HTTPStatusError as exc:
            self._record_provider_failure("polygon", started, exc, status_code=exc.response.status_code)
            return []
        except Exception as exc:
            self._record_provider_failure("polygon", started, exc)
            return []

    async def fetch_candles(self, ticker: str, span: str) -> list[dict]:
        ticker = ticker.upper()
        cfg = self._span_cfg(span)
        rows = await self._fetch_candles_alpaca(ticker, cfg)
        if rows:
            return rows
        if cfg.get("tiingo_daily"):
            rows = await self._fetch_candles_tiingo(ticker, cfg)
            if rows:
                return rows
        # Final fallback: Polygon aggregate endpoint (often delayed on free plans).
        rows = await self._fetch_candles_polygon(ticker, cfg)
        if rows:
            return rows
        raise RuntimeError(f"No live candles returned for {ticker} across configured providers.")

    async def search_symbols(self, query: str) -> list[dict]:
        q = (query or "").strip()
        if len(q) < 1:
            return []
        if not settings.finnhub_api_key:
            raise RuntimeError("FINNHUB_API_KEY is required for live search.")
        gate_errors: list[str] = []
        if not self._provider_can_attempt("finnhub", gate_errors):
            raise RuntimeError(f"Live symbol search temporarily unavailable: {', '.join(gate_errors)}")

        url = "https://finnhub.io/api/v1/search"
        started = datetime.utcnow()
        try:
            resp = await self.client.get(url, params={"q": q, "token": settings.finnhub_api_key})
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self._record_provider_failure("finnhub", started, exc, status_code=exc.response.status_code)
            raise
        except Exception as exc:
            self._record_provider_failure("finnhub", started, exc)
            raise
        items = resp.json().get("result", [])
        self._record_provider("finnhub", True, latency_ms=(datetime.utcnow() - started).total_seconds() * 1000.0)
        out: list[dict] = []
        for item in items:
            symbol = str(item.get("symbol", "")).upper()
            display_symbol = str(item.get("displaySymbol", "")).upper()
            desc = str(item.get("description", ""))
            type_ = str(item.get("type", ""))
            if not symbol or len(symbol) > 12:
                continue
            if "." in symbol and not symbol.endswith(".US"):
                continue
            if type_ and type_.lower() not in {"common stock", "etf", "adr", "index", "reit"}:
                continue
            out.append(
                {
                    "symbol": symbol,
                    "display_symbol": display_symbol or symbol,
                    "description": desc,
                    "type": type_,
                }
            )
            if len(out) >= 20:
                break
        return out

    async def sync_us_symbols(self, db: AsyncSession) -> dict:
        if not settings.finnhub_api_key:
            raise RuntimeError("FINNHUB_API_KEY is required for symbol sync.")
        gate_errors: list[str] = []
        if not self._provider_can_attempt("finnhub", gate_errors):
            raise RuntimeError(f"Symbol sync temporarily unavailable: {', '.join(gate_errors)}")

        url = "https://finnhub.io/api/v1/stock/symbol"
        started = datetime.utcnow()
        try:
            resp = await self.client.get(
                url,
                params={"exchange": "US", "token": settings.finnhub_api_key},
                follow_redirects=True,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self._record_provider_failure("finnhub", started, exc, status_code=exc.response.status_code)
            raise
        except Exception as exc:
            self._record_provider_failure("finnhub", started, exc)
            raise
        items = resp.json()
        self._record_provider("finnhub", True, latency_ms=(datetime.utcnow() - started).total_seconds() * 1000.0)

        upserted = 0
        for item in items:
            symbol = str(item.get("symbol", "")).upper().strip()
            if not symbol or len(symbol) > 24:
                continue
            description = str(item.get("description", "")).strip()
            type_ = str(item.get("type", "")).strip()
            display = str(item.get("displaySymbol", symbol)).strip()
            currency = str(item.get("currency", "")).strip()
            mic = str(item.get("mic", "")).strip()

            row = await db.get(SymbolMaster, symbol)
            if row is None:
                row = SymbolMaster(
                    symbol=symbol,
                    name=description,
                    exchange="US",
                    type=type_,
                    display_symbol=display,
                    currency=currency,
                    mic=mic,
                    updated_at=datetime.utcnow(),
                )
                db.add(row)
            else:
                row.name = description
                row.type = type_
                row.display_symbol = display
                row.currency = currency
                row.mic = mic
                row.updated_at = datetime.utcnow()
            upserted += 1

        await db.commit()
        return {"upserted": upserted}

    async def search_symbols_db(self, db: AsyncSession, query: str, limit: int = 20) -> list[dict]:
        q = (query or "").strip()
        if not q:
            return []
        symbol_prefix = f"{q.upper()}%"
        name_like = f"%{q}%"
        stmt = (
            select(SymbolMaster)
            .where(or_(SymbolMaster.symbol.ilike(symbol_prefix), SymbolMaster.name.ilike(name_like)))
            .order_by(SymbolMaster.symbol.asc())
            .limit(limit)
        )
        rows = list((await db.execute(stmt)).scalars().all())
        return [
            {
                "symbol": r.symbol,
                "display_symbol": r.display_symbol or r.symbol,
                "description": r.name,
                "type": r.type,
                "exchange": r.exchange,
            }
            for r in rows
        ]

    async def save_quote(self, db: AsyncSession, payload: dict) -> StockPrice:
        quote = StockPrice(**payload)
        db.add(quote)
        await db.commit()
        await db.refresh(quote)
        return quote

    async def get_latest_quote(self, db: AsyncSession, ticker: str) -> StockPrice | None:
        stmt = (
            select(StockPrice)
            .where(StockPrice.ticker == ticker.upper())
            .order_by(StockPrice.timestamp.desc())
            .limit(1)
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    async def get_price_history(self, db: AsyncSession, ticker: str, limit: int = 120) -> list[StockPrice]:
        stmt = (
            select(StockPrice)
            .where(StockPrice.ticker == ticker.upper())
            .order_by(StockPrice.timestamp.desc())
            .limit(limit)
        )
        rows = (await db.execute(stmt)).scalars().all()
        return list(reversed(rows))

    async def get_trending(self, db: AsyncSession, tickers: list[str]) -> list[dict]:
        output: list[dict] = []
        for ticker in tickers:
            latest = await self.get_latest_quote(db, ticker)
            if latest:
                output.append({
                    "ticker": ticker,
                    "price": latest.price,
                    "change_percent": latest.change_percent,
                    "volume": latest.volume,
                    "timestamp": latest.timestamp,
                })
        output.sort(key=lambda r: (r["change_percent"], r["volume"]), reverse=True)
        return output[:10]

    async def get_bull_cases(self, db: AsyncSession, tickers: list[str]) -> list[dict]:
        picks: list[dict] = []
        for ticker in tickers:
            rows = await self.get_price_history(db, ticker, limit=24)
            if len(rows) < 8:
                continue

            latest = rows[-1]
            lookback = rows[-8]
            prices = [r.price for r in rows[-8:]]
            volumes = [float(r.volume) for r in rows[-8:]]

            momentum_pct = ((latest.price / lookback.price) - 1.0) * 100 if lookback.price else 0.0
            avg_volume = sum(volumes[:-1]) / max(1, len(volumes) - 1)
            volume_ratio = (volumes[-1] / avg_volume) if avg_volume > 0 else 0.0
            up_steps = sum(1 for i in range(1, len(prices)) if prices[i] > prices[i - 1])

            if latest.change_percent <= 0 or momentum_pct <= 0.2:
                continue

            score = (latest.change_percent * 0.5) + (momentum_pct * 0.35) + (max(0.0, volume_ratio - 1.0) * 10 * 0.15)
            reasons: list[str] = []
            reasons.append(f"up {latest.change_percent:.2f}% today")
            reasons.append(f"{momentum_pct:.2f}% short-term momentum")
            if volume_ratio >= 1.3:
                reasons.append(f"volume {volume_ratio:.2f}x above recent average")
            if up_steps >= 5:
                reasons.append("consistent higher prints in recent bars")

            picks.append(
                {
                    "ticker": ticker,
                    "price": latest.price,
                    "change_percent": latest.change_percent,
                    "momentum_percent": round(momentum_pct, 2),
                    "volume_ratio": round(volume_ratio, 2),
                    "score": round(score, 3),
                    "reasons": reasons,
                    "timestamp": latest.timestamp,
                }
            )

        picks.sort(key=lambda x: x["score"], reverse=True)
        return picks[:12]

    async def _compute_signal_row(self, db: AsyncSession, ticker: str) -> dict | None:
        rows = await self.get_price_history(db, ticker, limit=80)
        if len(rows) < 20:
            return None
        latest = rows[-1]
        prev = rows[-2]
        lookback_7 = rows[-8] if len(rows) >= 8 else rows[0]
        lookback_20 = rows[-21] if len(rows) >= 21 else rows[0]
        prices = [float(r.price) for r in rows]
        volumes = [float(r.volume) for r in rows]
        avg_vol_20 = (sum(volumes[-21:-1]) / 20.0) if len(volumes) >= 21 else (sum(volumes[:-1]) / max(1, len(volumes) - 1))
        volume_ratio = (volumes[-1] / avg_vol_20) if avg_vol_20 > 0 else 0.0
        momentum_7 = ((latest.price / lookback_7.price) - 1.0) * 100.0 if lookback_7.price else 0.0
        momentum_20 = ((latest.price / lookback_20.price) - 1.0) * 100.0 if lookback_20.price else 0.0
        day_change = ((latest.price / prev.price) - 1.0) * 100.0 if prev.price else 0.0
        ma_7 = sum(prices[-7:]) / 7.0
        ma_20 = sum(prices[-20:]) / 20.0
        trend_gap = ((ma_7 - ma_20) / ma_20) * 100.0 if ma_20 else 0.0

        news_stmt = (
            select(NewsArticle)
            .where(NewsArticle.ticker == ticker.upper())
            .order_by(NewsArticle.published_at.desc())
            .limit(12)
        )
        news_rows = list((await db.execute(news_stmt)).scalars().all())
        sentiment = (sum(float(n.sentiment_score) for n in news_rows) / len(news_rows)) if news_rows else 0.0

        return {
            "ticker": ticker.upper(),
            "price": float(latest.price),
            "change_percent": float(latest.change_percent),
            "day_change": day_change,
            "momentum_7": momentum_7,
            "momentum_20": momentum_20,
            "volume_ratio": volume_ratio,
            "trend_gap": trend_gap,
            "sentiment": float(sentiment),
            "timestamp": latest.timestamp,
        }

    async def get_bull_cases_horizon(self, db: AsyncSession, tickers: list[str], horizon: str = "short") -> list[dict]:
        horizon_key = (horizon or "short").strip().lower()
        if horizon_key not in {"short", "mid", "long"}:
            horizon_key = "short"

        weights = {
            "short": {"momentum": 0.35, "sentiment": 0.25, "volume": 0.2, "trend": 0.2},
            "mid": {"momentum": 0.3, "sentiment": 0.25, "volume": 0.15, "trend": 0.3},
            "long": {"momentum": 0.2, "sentiment": 0.2, "volume": 0.1, "trend": 0.5},
        }[horizon_key]

        out: list[dict] = []
        for ticker in tickers:
            s = await self._compute_signal_row(db, ticker)
            if s is None:
                continue
            momentum_component = s["momentum_7"] if horizon_key == "short" else s["momentum_20"]
            sentiment_component = s["sentiment"] * 100.0
            volume_component = max(0.0, s["volume_ratio"] - 1.0) * 35.0
            trend_component = s["trend_gap"] * 3.0
            raw_score = (
                (weights["momentum"] * momentum_component)
                + (weights["sentiment"] * sentiment_component)
                + (weights["volume"] * volume_component)
                + (weights["trend"] * trend_component)
            )
            score = max(0.0, min(100.0, 50.0 + raw_score))

            reasons: list[str] = []
            if momentum_component > 0:
                reasons.append(f"momentum +{momentum_component:.2f}%")
            if s["sentiment"] > 0.05:
                reasons.append("positive news sentiment")
            if s["volume_ratio"] >= 1.2:
                reasons.append(f"volume spike {s['volume_ratio']:.2f}x")
            if s["trend_gap"] > 0:
                reasons.append("trend continuation")
            if not reasons:
                reasons.append("mixed signals")

            out.append(
                {
                    "ticker": s["ticker"],
                    "price": s["price"],
                    "change_percent": s["change_percent"],
                    "momentum_percent": round(momentum_component, 2),
                    "volume_ratio": round(s["volume_ratio"], 2),
                    "score": round(score, 2),
                    "horizon": horizon_key,
                    "reasons": reasons,
                    "timestamp": s["timestamp"],
                }
            )

        out.sort(key=lambda x: x["score"], reverse=True)
        return out[:12]

    async def get_market_pulse(self, db: AsyncSession, tickers: list[str]) -> dict:
        index_symbols = ["SPY", "QQQ", "DIA"]
        indices: dict[str, dict] = {}
        for symbol in index_symbols:
            row = await self.get_latest_quote(db, symbol)
            if row is None:
                try:
                    payload = await self.fetch_quote(symbol)
                    row = await self.save_quote(db, payload)
                except Exception:
                    row = None
            if row is not None:
                indices[symbol] = {
                    "symbol": symbol,
                    "price": float(row.price),
                    "change_percent": float(row.change_percent),
                }

        universe = sorted(set(tickers))[:80]
        rows: list[dict] = []
        for ticker in universe:
            sig = await self._compute_signal_row(db, ticker)
            if sig is not None:
                rows.append(sig)

        sorted_by_change = sorted(rows, key=lambda r: r["change_percent"], reverse=True)
        gainers = [
            {"symbol": r["ticker"], "price": round(r["price"], 4), "change_percent": round(r["change_percent"], 4)}
            for r in sorted_by_change[:8]
        ]
        losers = [
            {"symbol": r["ticker"], "price": round(r["price"], 4), "change_percent": round(r["change_percent"], 4)}
            for r in sorted_by_change[-8:]
        ]
        unusual_volume = sorted(rows, key=lambda r: r["volume_ratio"], reverse=True)[:8]
        unusual = [
            {
                "symbol": r["ticker"],
                "price": round(r["price"], 4),
                "volume_ratio": round(r["volume_ratio"], 3),
                "change_percent": round(r["change_percent"], 4),
            }
            for r in unusual_volume
            if r["volume_ratio"] > 1.05
        ]

        return {
            "indices": indices,
            "top_gainers": gainers,
            "top_losers": losers,
            "unusual_volume": unusual,
            "as_of": datetime.utcnow(),
        }

    async def get_watchlist_intelligence(self, db: AsyncSession, symbols: list[str]) -> list[dict]:
        rows: list[dict] = []
        for symbol in symbols:
            sig = await self._compute_signal_row(db, symbol)
            if sig is None:
                continue
            sentiment_label = "positive" if sig["sentiment"] > 0.07 else "negative" if sig["sentiment"] < -0.07 else "neutral"
            momentum_label = "bullish" if sig["momentum_7"] > 0.75 else "bearish" if sig["momentum_7"] < -0.75 else "neutral"
            risk_score = abs(sig["momentum_7"]) + abs(sig["day_change"]) + max(0.0, (sig["volume_ratio"] - 1.0) * 2.5)
            if risk_score >= 6:
                risk = "high"
            elif risk_score >= 2.5:
                risk = "medium"
            else:
                risk = "low"

            analyst_rating = "buy" if sig["trend_gap"] > 0.5 and sig["sentiment"] >= -0.1 else "sell" if sig["trend_gap"] < -0.5 else "hold"
            rows.append(
                {
                    "symbol": sig["ticker"],
                    "price": round(sig["price"], 4),
                    "change_percent": round(sig["change_percent"], 4),
                    "sentiment": sentiment_label,
                    "momentum": momentum_label,
                    "analyst_rating": analyst_rating,
                    "risk_level": risk,
                    "volume_ratio": round(sig["volume_ratio"], 3),
                    "as_of": sig["timestamp"],
                }
            )
        return rows

    async def compute_technical_snapshot(self, db: AsyncSession, ticker: str) -> dict | None:
        rows = await self.get_price_history(db, ticker, limit=260)
        if len(rows) < 40:
            return None

        frame = pd.DataFrame(
            [
                {
                    "close": float(r.price),
                    "high": float(r.high_price or r.price),
                    "low": float(r.low_price or r.price),
                    "volume": float(r.volume),
                    "timestamp": r.timestamp,
                }
                for r in rows
            ]
        )
        close = frame["close"]
        high = frame["high"]
        low = frame["low"]
        vol = frame["volume"]

        rsi = compute_rsi(close, period=14)
        macd, macd_sig = compute_macd(close)
        bbu, bbl = compute_bollinger(close, window=20, num_std=2.0)
        adx = compute_adx(high, low, close, period=14)
        obv = compute_obv(close, vol)
        vwap = compute_vwap(high, low, close, vol)
        roc5 = compute_roc(close, 5)
        roc20 = compute_roc(close, 20)
        sma20 = close.rolling(20, min_periods=20).mean().fillna(close)
        sma50 = close.rolling(50, min_periods=50).mean().fillna(close)
        sma200 = close.rolling(200, min_periods=200).mean().fillna(close)
        avg_vol_30 = vol.rolling(30, min_periods=20).mean().fillna(vol)
        volume_spike = (vol / avg_vol_30.replace(0, np.nan)).fillna(1.0)

        last_ts = frame["timestamp"].iloc[-1]
        snapshot = {
            "ticker": ticker.upper(),
            "timestamp": last_ts,
            "rsi": float(rsi.iloc[-1]),
            "macd": float(macd.iloc[-1]),
            "macd_signal": float(macd_sig.iloc[-1]),
            "adx": float(adx.iloc[-1]),
            "bollinger_upper": float(bbu.iloc[-1]),
            "bollinger_lower": float(bbl.iloc[-1]),
            "sma20": float(sma20.iloc[-1]),
            "sma50": float(sma50.iloc[-1]),
            "sma200": float(sma200.iloc[-1]),
            "roc_5": float(roc5.iloc[-1]),
            "roc_20": float(roc20.iloc[-1]),
            "obv": float(obv.iloc[-1]),
            "vwap": float(vwap.iloc[-1]),
            "volume_spike": float(volume_spike.iloc[-1]),
        }

        existing_stmt = (
            select(TechnicalIndicator)
            .where(TechnicalIndicator.ticker == ticker.upper(), TechnicalIndicator.timestamp == last_ts)
            .limit(1)
        )
        existing = (await db.execute(existing_stmt)).scalar_one_or_none()
        if existing is None:
            db.add(TechnicalIndicator(**snapshot))
            await db.commit()
        return snapshot

    async def get_latest_technical(self, db: AsyncSession, ticker: str) -> dict | None:
        stmt = (
            select(TechnicalIndicator)
            .where(TechnicalIndicator.ticker == ticker.upper())
            .order_by(TechnicalIndicator.timestamp.desc())
            .limit(1)
        )
        row = (await db.execute(stmt)).scalar_one_or_none()
        if row is None:
            return await self.compute_technical_snapshot(db, ticker)
        return {
            "ticker": row.ticker,
            "timestamp": row.timestamp,
            "rsi": float(row.rsi),
            "macd": float(row.macd),
            "macd_signal": float(row.macd_signal),
            "adx": float(row.adx),
            "bollinger_upper": float(row.bollinger_upper),
            "bollinger_lower": float(row.bollinger_lower),
            "sma20": float(row.sma20),
            "sma50": float(row.sma50),
            "sma200": float(row.sma200),
            "roc_5": float(row.roc_5),
            "roc_20": float(row.roc_20),
            "obv": float(row.obv),
            "vwap": float(row.vwap),
            "volume_spike": float(row.volume_spike),
        }

    async def _market_regime(self, db: AsyncSession) -> dict:
        spy_rows = await self.get_price_history(db, "SPY", limit=90)
        vix_rows = await self.get_price_history(db, "VIX", limit=30)
        if len(spy_rows) < 40:
            return {"regime": "sideways", "confidence": 0.4}
        closes = np.array([float(r.price) for r in spy_rows], dtype=float)
        ret_20 = (closes[-1] / closes[-21] - 1.0) * 100.0 if len(closes) > 21 and closes[-21] else 0.0
        vol_20 = float(np.std(np.diff(np.log(np.clip(closes[-21:], 1e-9, None)))) * np.sqrt(252) * 100.0)
        vix_now = float(vix_rows[-1].price) if vix_rows else 18.0
        if ret_20 > 2.0 and vix_now < 23 and vol_20 < 35:
            return {"regime": "bull", "confidence": 0.72}
        if ret_20 < -2.0 or vix_now > 28:
            return {"regime": "bear", "confidence": 0.7}
        return {"regime": "sideways", "confidence": 0.55}

    async def get_market_regime(self, db: AsyncSession) -> dict:
        return await self._market_regime(db)

    async def get_alpha_ranking(self, db: AsyncSession, tickers: list[str], horizon: str = "short") -> list[dict]:
        horizon_key = (horizon or "short").strip().lower()
        if horizon_key not in {"short", "mid", "long"}:
            horizon_key = "short"

        regime = await self._market_regime(db)
        regime_name = regime["regime"]

        base_weights = {
            "momentum": 0.25,
            "volume_spike": 0.15,
            "sentiment": 0.15,
            "rsi": 0.10,
            "macd": 0.10,
            "sector_strength": 0.10,
            "volatility_adj_return": 0.10,
            "analyst_revision": 0.05,
        }
        weights = dict(base_weights)
        if regime_name == "bull":
            weights["momentum"] += 0.06
            weights["volatility_adj_return"] -= 0.03
            weights["sentiment"] += 0.02
        elif regime_name == "bear":
            weights["momentum"] -= 0.04
            weights["volatility_adj_return"] += 0.07
            weights["rsi"] += 0.02

        universe = sorted(set(tickers))
        rows: list[dict] = []
        for ticker in universe:
            price_rows = await self.get_price_history(db, ticker, limit=260)
            if len(price_rows) < 60:
                continue
            ti = await self.get_latest_technical(db, ticker)
            if ti is None:
                continue

            close = np.array([float(r.price) for r in price_rows], dtype=float)
            returns = np.diff(np.log(np.clip(close, 1e-9, None)))
            ret_1d = (close[-1] / close[-2] - 1.0) * 100.0 if close[-2] else 0.0
            ret_5d = (close[-1] / close[-6] - 1.0) * 100.0 if close[-6] else 0.0
            ret_20d = (close[-1] / close[-21] - 1.0) * 100.0 if close[-21] else 0.0
            momentum = ret_5d if horizon_key == "short" else ret_20d
            volatility_20 = float(np.std(returns[-20:]) * np.sqrt(252) * 100.0) if len(returns) >= 20 else 20.0
            volatility_adj_return = momentum / max(1.0, volatility_20)

            sentiment_rows = list(
                (await db.execute(select(NewsArticle).where(NewsArticle.ticker == ticker).order_by(NewsArticle.published_at.desc()).limit(12))).scalars().all()
            )
            sentiment = float(np.mean([float(n.sentiment_score) for n in sentiment_rows])) if sentiment_rows else 0.0
            analyst_revision = 0.0
            for n in sentiment_rows:
                h = (n.headline or "").lower()
                if "upgrade" in h or "raises price target" in h:
                    analyst_revision += 0.15
                if "downgrade" in h or "cuts price target" in h:
                    analyst_revision -= 0.15
            analyst_revision = max(-1.0, min(1.0, analyst_revision))

            # Sector strength proxy: compare stock 20D return to median universe 20D return.
            universe_ret20: list[float] = []
            for peer in universe[:40]:
                peer_rows = await self.get_price_history(db, peer, limit=30)
                if len(peer_rows) >= 21 and peer_rows[-21].price:
                    universe_ret20.append((peer_rows[-1].price / peer_rows[-21].price - 1.0) * 100.0)
            median_ret20 = float(np.median(universe_ret20)) if universe_ret20 else 0.0
            sector_strength = ret_20d - median_ret20

            volume_spike = float(ti["volume_spike"])
            rsi = float(ti["rsi"])
            macd = float(ti["macd"])
            macd_signal = float(ti["macd_signal"])

            rsi_factor = (50.0 - abs(rsi - 50.0)) / 50.0  # best near balanced regime
            macd_factor = 1.0 if macd > macd_signal else -1.0

            momentum_norm = np.tanh(momentum / 8.0)
            vol_spike_norm = np.tanh((volume_spike - 1.0) / 1.5)
            sentiment_norm = np.tanh(sentiment * 1.8)
            sector_norm = np.tanh(sector_strength / 8.0)
            var_norm = np.tanh(volatility_adj_return / 1.8)
            analyst_norm = np.tanh(analyst_revision * 2.0)

            alpha = (
                weights["momentum"] * momentum_norm
                + weights["volume_spike"] * vol_spike_norm
                + weights["sentiment"] * sentiment_norm
                + weights["rsi"] * rsi_factor
                + weights["macd"] * macd_factor
                + weights["sector_strength"] * sector_norm
                + weights["volatility_adj_return"] * var_norm
                + weights["analyst_revision"] * analyst_norm
            )
            alpha_score = float((alpha + 1.0) / 2.0)  # 0..1

            beta_proxy = abs(ret_1d) / max(0.01, abs(ret_20d) / 20.0) if ret_20d else 1.0
            risk_score = min(100.0, max(0.0, 0.5 * volatility_20 + 15.0 * min(3.0, beta_proxy)))
            risk_level = "high" if risk_score >= 70 else "medium" if risk_score >= 40 else "low"

            rows.append(
                {
                    "symbol": ticker,
                    "alpha_score": round(alpha_score, 4),
                    "horizon": horizon_key,
                    "regime": regime_name,
                    "risk_score": round(risk_score, 2),
                    "risk_level": risk_level,
                    "factors": {
                        "momentum": round(float((momentum_norm + 1.0) / 2.0), 4),
                        "volume": round(float((vol_spike_norm + 1.0) / 2.0), 4),
                        "sentiment": round(float((sentiment_norm + 1.0) / 2.0), 4),
                        "sector_strength": round(float((sector_norm + 1.0) / 2.0), 4),
                        "momentum_1d": round(ret_1d, 4),
                        "momentum_5d": round(ret_5d, 4),
                        "momentum_20d": round(ret_20d, 4),
                        "volume_anomaly": round(volume_spike, 4),
                        "volatility_20d": round(volatility_20, 4),
                        "rsi": round(rsi, 4),
                        "macd": round(macd, 6),
                        "macd_signal": round(macd_signal, 6),
                        "sentiment": round(sentiment, 4),
                        "sector_strength": round(sector_strength, 4),
                        "volatility_adjusted_return": round(volatility_adj_return, 4),
                        "analyst_revision": round(analyst_revision, 4),
                    },
                }
            )

        rows.sort(key=lambda x: x["alpha_score"], reverse=True)
        return rows[:25]

    async def run_backtest(self, db: AsyncSession, symbol: str, strategy: str = "rsi_oversold", lookback_days: int = 252 * 2) -> dict:
        ticker = symbol.upper()
        rows = await self.get_price_history(db, ticker, limit=max(300, lookback_days + 40))
        if len(rows) < 80:
            return {"symbol": ticker, "strategy": strategy, "error": "insufficient history"}

        frame = pd.DataFrame(
            [{"close": float(r.price), "high": float(r.high_price or r.price), "low": float(r.low_price or r.price), "volume": float(r.volume), "timestamp": r.timestamp} for r in rows]
        )
        frame["rsi"] = compute_rsi(frame["close"], 14)
        macd, macd_signal = compute_macd(frame["close"])
        frame["macd"] = macd
        frame["macd_signal"] = macd_signal
        frame["ret_fwd_5"] = (frame["close"].shift(-5) / frame["close"] - 1.0) * 100.0
        frame = frame.dropna().tail(lookback_days)

        if strategy == "rsi_oversold":
            entries = frame[(frame["rsi"] < 30) & (frame["macd"] > frame["macd_signal"])]
        elif strategy == "macd_trend":
            entries = frame[(frame["macd"] > frame["macd_signal"]) & (frame["rsi"] > 45)]
        else:
            entries = frame[(frame["rsi"] < 35)]

        if entries.empty:
            return {
                "symbol": ticker,
                "strategy": strategy,
                "trades": 0,
                "win_rate": 0.0,
                "avg_return": 0.0,
                "max_drawdown": 0.0,
                "cumulative_return": 0.0,
            }

        trade_returns = entries["ret_fwd_5"].astype(float).to_numpy()
        win_rate = float(np.mean(trade_returns > 0))
        avg_return = float(np.mean(trade_returns))
        equity = np.cumprod(1.0 + trade_returns / 100.0)
        peak = np.maximum.accumulate(equity)
        drawdown = (equity - peak) / peak
        max_drawdown = float(abs(np.min(drawdown)) * 100.0) if len(drawdown) else 0.0
        cumulative = float((equity[-1] - 1.0) * 100.0) if len(equity) else 0.0

        return {
            "symbol": ticker,
            "strategy": strategy,
            "trades": int(len(trade_returns)),
            "win_rate": round(win_rate, 4),
            "avg_return": round(avg_return, 4),
            "max_drawdown": round(max_drawdown, 4),
            "cumulative_return": round(cumulative, 4),
            "lookback_days": lookback_days,
        }
