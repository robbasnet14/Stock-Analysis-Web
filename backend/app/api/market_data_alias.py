from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.schemas.common import StockTick
from app.state import state


router = APIRouter(tags=["market-data"])


def _normalize_quote_payload(symbol: str, payload: dict) -> dict:
    px = float(payload.get("price") or 0.0)
    open_px = float(payload.get("open_price") or px)
    high_px = float(payload.get("high_price") or px or open_px)
    low_px = float(payload.get("low_price") or px or open_px)
    ts = payload.get("timestamp")
    if not isinstance(ts, datetime):
        ts = datetime.utcnow()
    return {
        "ticker": symbol.upper(),
        "price": px,
        "change_percent": float(payload.get("change_percent") or 0.0),
        "volume": int(float(payload.get("volume") or 0)),
        "open_price": open_px,
        "high_price": high_px,
        "low_price": low_px,
        "timestamp": ts,
        "source": str(payload.get("source") or "provider_router"),
        "is_live": True,
    }


def _normalize_candles(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    prev_close: float | None = None
    for row in sorted(rows, key=lambda x: x.get("timestamp") or datetime.utcnow()):
        close = float(row.get("price") or 0.0)
        if close <= 0:
            continue
        ts = row.get("timestamp")
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                ts = datetime.utcnow()
        if not isinstance(ts, datetime):
            ts = datetime.utcnow()
        if prev_close and prev_close > 0:
            change_percent = ((close - prev_close) / prev_close) * 100.0
        else:
            change_percent = float(row.get("change_percent") or 0.0)
        out.append(
            {
                "price": close,
                "volume": float(row.get("volume") or 0.0),
                "change_percent": float(change_percent),
                "open_price": float(row.get("open_price") or close),
                "high_price": float(row.get("high_price") or close),
                "low_price": float(row.get("low_price") or close),
                "timestamp": ts,
            }
        )
        prev_close = close
    return out


@router.get("/quote/{ticker}", response_model=StockTick)
async def quote_alias(ticker: str, db: AsyncSession = Depends(get_db)) -> StockTick:
    symbol = ticker.upper()
    state.watchlist.add(symbol)
    try:
        payload = await state.market_data.get_quote(symbol)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Live quote unavailable: {exc}") from exc

    normalized = _normalize_quote_payload(symbol, payload)
    try:
        await state.stock_service.save_quote(db, normalized)
    except Exception:
        pass

    return StockTick(
        ticker=normalized["ticker"],
        price=float(normalized["price"]),
        change_percent=float(normalized["change_percent"]),
        volume=float(normalized["volume"]),
        open_price=float(normalized["open_price"]),
        high_price=float(normalized["high_price"]),
        low_price=float(normalized["low_price"]),
        timestamp=normalized["timestamp"],
        source=str(normalized.get("source") or ""),
    )


@router.get("/bars/{ticker}")
async def bars_alias(
    ticker: str,
    tf: str = "1min",
    range: str = "1D",
    db: AsyncSession = Depends(get_db),
) -> dict:
    tf_raw = (tf or "").strip()
    try:
        payload = await state.market_data.get_bars(ticker, range, tf=tf_raw or None)
        return payload
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        fallback_limit = 390 if range.upper() == "1D" else 500
        stored = await state.stock_service.get_price_history(db, ticker, limit=fallback_limit)
        if not stored:
            raise HTTPException(status_code=503, detail=f"Live bars unavailable: {exc}") from exc
        rows = [
            {
                "timestamp": (r.timestamp if isinstance(r.timestamp, datetime) else datetime.now(timezone.utc)).astimezone(
                    timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "open": float(r.open_price or r.price),
                "high": float(r.high_price or r.price),
                "low": float(r.low_price or r.price),
                "close": float(r.price),
                "volume": float(r.volume),
            }
            for r in stored
        ]

    return {
        "ticker": ticker.upper(),
        "tf": tf_raw or "1Min",
        "range": range.upper(),
        "source": "db",
        "start": "",
        "end": "",
        "bars": rows,
        "data": rows,
    }
