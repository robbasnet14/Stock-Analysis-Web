from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.dependencies import get_optional_user
from app.models.user import User
from app.models.symbol import SymbolMaster
from app.models.symbol_fundamental import SymbolFundamental
from app.models.watchlist import WatchlistItem
from app.schemas.common import StockTick
from app.config import get_settings
from app.services.market_session import get_market_session
from app.state import state


router = APIRouter(prefix="/stocks", tags=["stocks"])
settings = get_settings()


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
    if not rows:
        return []
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


class AlertCreate(BaseModel):
    ticker: str
    target_price: float
    direction: str = "above"


class WatchlistRequest(BaseModel):
    ticker: str


async def _effective_watchlist(db: AsyncSession, user: User | None) -> list[str]:
    if user is not None:
        stmt = select(WatchlistItem).where(WatchlistItem.user_id == user.id).order_by(WatchlistItem.symbol.asc())
        rows = [r.symbol for r in (await db.execute(stmt)).scalars().all()]
        if rows:
            return rows
    return sorted(state.watchlist) if state.watchlist else ["AAPL", "MSFT", "TSLA", "NVDA", "AMZN"]


@router.get("/watchlist")
async def get_watchlist(db: AsyncSession = Depends(get_db), user: User | None = Depends(get_optional_user)) -> dict:
    if user is not None:
        stmt = select(WatchlistItem).where(WatchlistItem.user_id == user.id).order_by(WatchlistItem.symbol.asc())
        rows = [r.symbol for r in (await db.execute(stmt)).scalars().all()]
        return {"watchlist": rows}
    return {"watchlist": sorted(state.watchlist)}


@router.get("/live-status")
async def live_status() -> dict:
    configured = {
        "alpaca_data": bool(settings.alpaca_api_key and settings.alpaca_secret_key),
        "finnhub": bool(settings.finnhub_api_key),
        "polygon": bool(settings.polygon_api_key),
        "tiingo": bool(settings.tiingo_api_key),
    }
    active = [k for k, v in configured.items() if v]
    return {
        "live_data_only": settings.live_data_only,
        "finnhub_configured": configured["finnhub"],
        "providers_configured": configured,
        "provider": active[0] if active else "none",
    }


@router.get("/session")
async def market_session() -> dict:
    return get_market_session()


@router.post("/watchlist/add")
async def add_watchlist(
    item: WatchlistRequest,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> dict:
    ticker = item.ticker.upper()
    state.watchlist.add(ticker)
    if user is not None:
        stmt = select(WatchlistItem).where(WatchlistItem.user_id == user.id, WatchlistItem.symbol == ticker)
        row = (await db.execute(stmt)).scalar_one_or_none()
        if row is None:
            db.add(WatchlistItem(user_id=user.id, symbol=ticker))
            await db.commit()
        stmt = select(WatchlistItem).where(WatchlistItem.user_id == user.id).order_by(WatchlistItem.symbol.asc())
        rows = [r.symbol for r in (await db.execute(stmt)).scalars().all()]
        return {"watchlist": rows}
    state.watchlist.add(ticker)
    return {"watchlist": sorted(state.watchlist)}


@router.post("/watchlist/remove")
async def remove_watchlist(
    item: WatchlistRequest,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> dict:
    ticker = item.ticker.upper()
    if user is not None:
        stmt = select(WatchlistItem).where(WatchlistItem.user_id == user.id, WatchlistItem.symbol == ticker)
        row = (await db.execute(stmt)).scalar_one_or_none()
        if row is not None:
            await db.delete(row)
            await db.commit()
        stmt = select(WatchlistItem).where(WatchlistItem.user_id == user.id).order_by(WatchlistItem.symbol.asc())
        rows = [r.symbol for r in (await db.execute(stmt)).scalars().all()]
        return {"watchlist": rows}
    state.watchlist.discard(ticker)
    return {"watchlist": sorted(state.watchlist)}


@router.get("/symbols/status")
async def symbols_status(db: AsyncSession = Depends(get_db)) -> dict:
    count = await db.scalar(select(func.count(SymbolMaster.symbol)))
    return {"symbols_count": int(count or 0)}


@router.post("/symbols/sync")
async def sync_symbols(db: AsyncSession = Depends(get_db)) -> dict:
    try:
        rows = await state.market_data.symbol_master()
        upserted = 0
        for item in rows:
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
        count = await db.scalar(select(func.count(SymbolMaster.symbol)))
        return {"ok": True, "upserted": upserted, "symbols_count": int(count or 0)}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Symbol sync failed: {exc}") from exc


@router.get("/search")
async def search_symbols(q: str, db: AsyncSession = Depends(get_db)) -> dict:
    if len((q or "").strip()) < 1:
        return {"results": []}

    db_rows = await state.stock_service.search_symbols_db(db, q, limit=20)
    if db_rows:
        return {"results": db_rows}

    try:
        rows = await state.market_data.search(q)
        return {"results": rows}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Live symbol search unavailable: {exc}") from exc


@router.get("/{ticker}/latest")
async def latest_stock(ticker: str, db: AsyncSession = Depends(get_db)) -> StockTick:
    symbol = ticker.upper()
    state.watchlist.add(symbol)

    if state.redis is not None:
        cached = await state.redis.get(f"latest:{symbol}")
        if cached:
            try:
                import json
                payload = json.loads(cached)
                return StockTick(
                    ticker=symbol,
                    price=float(payload.get("price", 0.0)),
                    change_percent=float(payload.get("change_percent", 0.0)),
                    volume=float(payload.get("volume", 0.0)),
                    open_price=float(payload.get("open_price", payload.get("price", 0.0))),
                    high_price=float(payload.get("high_price", payload.get("price", 0.0))),
                    low_price=float(payload.get("low_price", payload.get("price", 0.0))),
                    timestamp=datetime.fromisoformat(str(payload.get("timestamp")).replace("Z", "")),
                    source=str(payload.get("source") or ""),
                )
            except Exception:
                pass

    try:
        payload = await state.market_data.get_quote(ticker)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Live quote unavailable: {exc}") from exc

    normalized = _normalize_quote_payload(symbol, payload)
    try:
        await state.stock_service.save_quote(db, normalized)
    except Exception:
        # Keep endpoint live even if local DB schema lags behind.
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


@router.get("/quote/{ticker}")
async def quote_alias(ticker: str, db: AsyncSession = Depends(get_db)) -> StockTick:
    return await latest_stock(ticker=ticker, db=db)


@router.get("/{ticker}/history")
async def stock_history(ticker: str, limit: int = 120, db: AsyncSession = Depends(get_db)) -> dict:
    rows = await state.stock_service.get_price_history(db, ticker, limit=limit)
    return {
        "ticker": ticker.upper(),
        "data": [
            {
                "price": row.price,
                "volume": row.volume,
                "change_percent": row.change_percent,
                "open_price": row.open_price,
                "high_price": row.high_price,
                "low_price": row.low_price,
                "timestamp": row.timestamp,
            }
            for row in rows
        ],
    }


@router.get("/{ticker}/candles")
async def stock_candles(ticker: str, range: str = "1D", db: AsyncSession = Depends(get_db)) -> list[dict]:
    rows: list[dict] = []
    try:
        payload = await state.market_data.get_bars(ticker, range, tf="1Day")
        rows = payload.get("bars") or []
    except Exception as exc:
        fallback_limit = 390 if range.upper() == "1D" else 400
        stored = await state.stock_service.get_price_history(db, ticker, limit=fallback_limit)
        if stored:
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
        else:
            raise HTTPException(status_code=503, detail=f"Live candles unavailable: {exc}") from exc
    if not rows:
        fallback_limit = 390 if range.upper() == "1D" else 400
        stored = await state.stock_service.get_price_history(db, ticker, limit=fallback_limit)
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
    return rows


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


@router.get("/trending/list")
async def trending_stocks(db: AsyncSession = Depends(get_db), user: User | None = Depends(get_optional_user)) -> dict:
    tickers = await _effective_watchlist(db, user)
    data = await state.stock_service.get_trending(db, tickers)
    return {"trending": data}


@router.get("/bull-cases/list")
async def bull_cases(
    horizon: str = "short",
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> dict:
    tickers = await _effective_watchlist(db, user)
    data = await state.stock_service.get_bull_cases_horizon(db, tickers, horizon=horizon)
    return {"bull_cases": data, "horizon": horizon.lower(), "as_of": datetime.utcnow()}


@router.get("/signals/ranked")
async def ranked_signals(
    horizon: str = "short",
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> dict:
    tickers = await _effective_watchlist(db, user)
    rows = await state.stock_service.get_bull_cases_horizon(db, tickers, horizon=horizon)
    regime = await state.stock_service.get_market_regime(db)

    sectors_payload = await state.sector_service.get_sector_strength(db, tickers, redis_client=state.redis)
    sector_strength = {r["sector"]: float(r["strength"]) for r in sectors_payload.get("items", [])}

    sf_stmt = select(SymbolFundamental).where(SymbolFundamental.symbol.in_([r["ticker"] for r in rows]))
    sf_rows = list((await db.execute(sf_stmt)).scalars().all())
    symbol_sector = {s.symbol: s.sector for s in sf_rows}

    longs: list[dict] = []
    shorts: list[dict] = []
    regime_name = str(regime.get("regime", "sideways")).lower()
    regime_conf = float(regime.get("confidence", 0.5))

    for r in rows:
        sector = symbol_sector.get(r["ticker"], "other")
        sec = float(sector_strength.get(sector, 0.5))
        momentum = float(r.get("momentum_percent", 0.0))
        vol_ratio = float(r.get("volume_ratio", 1.0))
        daily = float(r.get("change_percent", 0.0))

        long_score = (
            0.40 * max(0.0, momentum)
            + 0.20 * max(0.0, (vol_ratio - 1.0) * 10.0)
            + 0.20 * max(0.0, daily)
            + 0.20 * (sec * 10.0)
        )
        short_score = (
            0.40 * max(0.0, -momentum)
            + 0.20 * max(0.0, (vol_ratio - 1.0) * 10.0)
            + 0.20 * max(0.0, -daily)
            + 0.20 * ((1.0 - sec) * 10.0)
        )

        if regime_name == "bull":
            long_score *= 1.0 + (0.15 * regime_conf)
            short_score *= 1.0 - (0.10 * regime_conf)
        elif regime_name == "bear":
            long_score *= 1.0 - (0.10 * regime_conf)
            short_score *= 1.0 + (0.15 * regime_conf)

        item = {
            "ticker": r["ticker"],
            "price": r["price"],
            "change_percent": daily,
            "momentum_percent": momentum,
            "volume_ratio": vol_ratio,
            "sector": sector,
            "sector_strength": round(sec, 4),
            "horizon": horizon.lower(),
            "timestamp": r["timestamp"],
        }
        longs.append({**item, "score": round(long_score, 4)})
        shorts.append({**item, "score": round(short_score, 4)})

    longs.sort(key=lambda x: x["score"], reverse=True)
    shorts.sort(key=lambda x: x["score"], reverse=True)
    return {
        "horizon": horizon.lower(),
        "regime": regime,
        "longs": longs[:10],
        "shorts": shorts[:10],
        "as_of": datetime.utcnow(),
    }


@router.get("/bullish")
async def bullish_stocks(
    horizon: str = "short",
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> list[dict]:
    tickers = await _effective_watchlist(db, user)
    data = await state.stock_service.get_bull_cases_horizon(db, tickers, horizon=horizon)
    return [{"symbol": item["ticker"], "score": round(float(item["score"]) / 100.0, 4)} for item in data]


@router.get("/alpha-ranking")
async def alpha_ranking(
    horizon: str = "short",
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> dict:
    tickers = await _effective_watchlist(db, user)
    ranked = await state.stock_service.get_alpha_ranking(db, tickers, horizon=horizon)
    regime = await state.stock_service.get_market_regime(db)
    return {
        "horizon": horizon.lower(),
        "regime": regime,
        "items": ranked,
        "as_of": datetime.utcnow(),
    }


@router.get("/market-regime")
async def market_regime(db: AsyncSession = Depends(get_db)) -> dict:
    regime = await state.stock_service.get_market_regime(db)
    return {"regime": regime, "as_of": datetime.utcnow()}


@router.get("/{ticker}/technical")
async def technical_snapshot(ticker: str, db: AsyncSession = Depends(get_db)) -> dict:
    out = await state.stock_service.get_latest_technical(db, ticker)
    if out is None:
        raise HTTPException(status_code=404, detail="Not enough price data to compute indicators")
    return out
