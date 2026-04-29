import asyncio
import json
from datetime import datetime, timedelta
from sqlalchemy import select
from websockets import connect
from app.config import get_settings
from app.db.database import SessionLocal
from app.models.watchlist import Watchlist
from app.state import state


settings = get_settings()


def _pick_stream_provider() -> str | None:
    pref = (settings.market_stream_provider or "auto").strip().lower()
    if pref == "alpaca":
        return "alpaca" if (settings.alpaca_api_key and settings.alpaca_secret_key) else None
    if pref == "polygon":
        return "polygon" if settings.polygon_api_key else None
    if pref == "finnhub":
        return "finnhub" if settings.finnhub_api_key else None
    if settings.alpaca_api_key and settings.alpaca_secret_key:
        return "alpaca"
    if settings.finnhub_api_key:
        return "finnhub"
    if settings.polygon_api_key:
        return "polygon"
    return None


def _iter_provider_trades(provider: str, msg: dict | list) -> list[dict]:
    out: list[dict] = []
    if provider == "alpaca":
        events = msg if isinstance(msg, list) else [msg]
        for ev in events:
            if not isinstance(ev, dict):
                continue
            typ = str(ev.get("T", "")).lower()
            if typ in {"success", "subscription", "error"}:
                continue
            sym = str(ev.get("S", "")).upper()
            if not sym:
                continue
            ts_raw = str(ev.get("t") or "")
            ts_dt = datetime.utcnow()
            if ts_raw:
                try:
                    ts_dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).replace(tzinfo=None)
                except Exception:
                    ts_dt = datetime.utcnow()

            # Trade event
            if typ == "t":
                price = float(ev.get("p") or 0.0)
                vol = float(ev.get("s") or 0.0)
            # Bar event
            elif typ == "b":
                price = float(ev.get("c") or 0.0)
                vol = float(ev.get("v") or 0.0)
            # Quote event: use mid if present
            elif typ == "q":
                ask = float(ev.get("ap") or 0.0)
                bid = float(ev.get("bp") or 0.0)
                price = ((ask + bid) / 2.0) if ask > 0 and bid > 0 else (ask or bid)
                vol = 0.0
            else:
                continue

            if price > 0:
                out.append({"sym": sym, "price": price, "volume": vol, "ts": ts_dt})
        return out

    if provider == "finnhub":
        payload = msg if isinstance(msg, dict) else {}
        if payload.get("type") != "trade":
            return []
        for t in payload.get("data") or []:
            sym = str(t.get("s", "")).upper()
            price = float(t.get("p") or 0.0)
            vol = float(t.get("v") or 0.0)
            ts_ms = int(t.get("t") or 0)
            if sym and price > 0:
                out.append({"sym": sym, "price": price, "volume": vol, "ts": datetime.utcfromtimestamp(ts_ms / 1000.0) if ts_ms else datetime.utcnow()})
        return out

    # Polygon websocket payload is usually a list of events
    events = msg if isinstance(msg, list) else [msg]
    for ev in events:
        if not isinstance(ev, dict):
            continue
        if str(ev.get("ev", "")).upper() != "T":
            continue
        sym = str(ev.get("sym", "")).upper()
        price = float(ev.get("p") or 0.0)
        vol = float(ev.get("s") or 0.0)
        ts_ms = int(ev.get("t") or 0)
        if sym and price > 0:
            out.append({"sym": sym, "price": price, "volume": vol, "ts": datetime.utcfromtimestamp(ts_ms / 1000.0) if ts_ms else datetime.utcnow()})
    return out


async def stream_market_forever() -> None:
    provider = _pick_stream_provider()
    if provider is None:
        if settings.live_data_only:
            return
        return

    if provider == "alpaca":
        ws_url = settings.alpaca_stream_url
    elif provider == "polygon":
        ws_url = "wss://socket.polygon.io/stocks"
    else:
        ws_url = f"wss://ws.finnhub.io?token={settings.finnhub_api_key}"
    throttle = max(0.25, float(settings.market_stream_throttle_seconds))

    while True:
        try:
            async with connect(ws_url, ping_interval=20, ping_timeout=20) as ws:
                subscribed: set[str] = set()
                snapshot_refresh_at = datetime.utcnow()
                symbol_state: dict[str, dict[str, float]] = {}
                last_saved_at: dict[str, datetime] = {}
                sec_agg: dict[str, dict[str, float | datetime]] = {}

                async def sync_subscriptions() -> None:
                    targets = set(sorted(state.watchlist) if state.watchlist else settings.ticker_list)
                    for sym in sorted(targets - subscribed):
                        if provider == "alpaca":
                            await ws.send(json.dumps({"action": "subscribe", "trades": [sym], "quotes": [sym], "bars": [sym]}))
                        elif provider == "polygon":
                            await ws.send(json.dumps({"action": "subscribe", "params": f"T.{sym}"}))
                        else:
                            await ws.send(json.dumps({"type": "subscribe", "symbol": sym}))
                        subscribed.add(sym)
                    for sym in sorted(subscribed - targets):
                        if provider == "alpaca":
                            await ws.send(json.dumps({"action": "unsubscribe", "trades": [sym], "quotes": [sym], "bars": [sym]}))
                        elif provider == "polygon":
                            await ws.send(json.dumps({"action": "unsubscribe", "params": f"T.{sym}"}))
                        else:
                            await ws.send(json.dumps({"type": "unsubscribe", "symbol": sym}))
                        subscribed.discard(sym)

                async def refresh_symbol_baseline() -> None:
                    async with SessionLocal() as db:
                        try:
                            quotes = await state.market_data.get_quotes(sorted(subscribed))
                        except Exception:
                            quotes = {}
                        for sym in sorted(subscribed):
                            try:
                                q = quotes.get(sym) or await state.market_data.get_quote(sym)
                                symbol_state[sym] = {
                                    "open": float(q.get("open_price", q.get("price", 0.0))),
                                    "high": float(q.get("high_price", q.get("price", 0.0))),
                                    "low": float(q.get("low_price", q.get("price", 0.0))),
                                    "change_percent": float(q.get("change_percent", 0.0)),
                                }
                            except Exception:
                                pass

                if provider == "alpaca":
                    await ws.send(json.dumps({"action": "auth", "key": settings.alpaca_api_key, "secret": settings.alpaca_secret_key}))
                elif provider == "polygon":
                    await ws.send(json.dumps({"action": "auth", "params": settings.polygon_api_key}))
                await sync_subscriptions()
                await refresh_symbol_baseline()

                while True:
                    if datetime.utcnow() >= snapshot_refresh_at:
                        await sync_subscriptions()
                        await refresh_symbol_baseline()
                        snapshot_refresh_at = datetime.utcnow() + timedelta(minutes=3)

                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    msg = json.loads(raw)
                    trades = _iter_provider_trades(provider, msg)
                    if not trades:
                        continue

                    now = datetime.utcnow()

                    async with SessionLocal() as db:
                        connected_watchlist_users = state.watchlist_websocket.connected_user_ids()
                        watchlist_targets: dict[str, set[int]] = {}
                        if connected_watchlist_users:
                            trade_symbols = {str(t.get("s", "")).upper() for t in trades if t.get("s")}
                            if trade_symbols:
                                wl_stmt = (
                                    select(Watchlist.user_id, Watchlist.symbol)
                                    .where(Watchlist.symbol.in_(trade_symbols), Watchlist.user_id.in_(connected_watchlist_users))
                                )
                                wl_rows = (await db.execute(wl_stmt)).all()
                                for user_id, symbol in wl_rows:
                                    watchlist_targets.setdefault(symbol, set()).add(int(user_id))

                        for t in trades:
                            sym = str(t["sym"]).upper()
                            price = float(t["price"])
                            volume = float(t["volume"])
                            event_ts: datetime = t["ts"] if isinstance(t.get("ts"), datetime) else now

                            baseline = symbol_state.get(sym, {"open": price, "high": price, "low": price, "change_percent": 0.0})
                            baseline["high"] = max(float(baseline.get("high", price)), price)
                            baseline["low"] = min(float(baseline.get("low", price)), price)
                            open_price = float(baseline.get("open", price)) or price
                            change_percent = ((price - open_price) / open_price * 100.0) if open_price else float(baseline.get("change_percent", 0.0))
                            symbol_state[sym] = {
                                "open": open_price,
                                "high": baseline["high"],
                                "low": baseline["low"],
                                "change_percent": change_percent,
                            }

                            # Build deterministic 1-second OHLCV aggregation for storage.
                            bucket = event_ts.replace(microsecond=0)
                            agg = sec_agg.get(sym)
                            if agg is None or agg["bucket"] != bucket:
                                # Flush previous second first
                                if agg is not None:
                                    prev_ts = last_saved_at.get(sym)
                                    if not prev_ts or (datetime.utcnow() - prev_ts).total_seconds() >= throttle:
                                        last_saved_at[sym] = datetime.utcnow()
                                        await state.stock_service.save_quote(
                                            db,
                                            {
                                                "ticker": sym,
                                                "price": float(agg["close"]),
                                                "change_percent": round(change_percent, 4),
                                                "volume": float(agg["volume"]),
                                                "open_price": float(agg["open"]),
                                                "high_price": float(agg["high"]),
                                                "low_price": float(agg["low"]),
                                                "timestamp": agg["bucket"],
                                            },
                                        )
                                sec_agg[sym] = {
                                    "bucket": bucket,
                                    "open": price,
                                    "high": price,
                                    "low": price,
                                    "close": price,
                                    "volume": volume,
                                }
                            else:
                                agg["high"] = max(float(agg["high"]), price)
                                agg["low"] = min(float(agg["low"]), price)
                                agg["close"] = price
                                agg["volume"] = float(agg["volume"]) + volume

                            prediction = await state.ml_service.latest_prediction(db, sym)
                            live_agg = sec_agg.get(sym) or {"open": price, "high": price, "low": price, "close": price, "volume": volume}
                            payload = {
                                "type": "tick",
                                "ticker": sym,
                                "price": price,
                                "change_percent": round(change_percent, 4),
                                "volume": float(live_agg["volume"]),
                                "open_price": float(live_agg["open"]),
                                "high_price": float(live_agg["high"]),
                                "low_price": float(live_agg["low"]),
                                "timestamp": bucket.isoformat(),
                                "prediction": prediction,
                            }

                            if state.redis is not None:
                                await state.redis.set(f"price:{sym}", str(price), ex=120)
                                await state.redis.hset("price:latest", sym, str(price))
                                await state.redis.set(f"latest:{sym}", json.dumps(payload, default=str), ex=120)
                                await state.redis.publish(f"stream:{sym}", json.dumps(payload, default=str))

                            await state.websocket.broadcast(sym, payload)
                            if sym in watchlist_targets:
                                watch_payload = {
                                    "type": "price_update",
                                    "symbol": sym,
                                    "price": float(price),
                                    "timestamp": int(bucket.timestamp()),
                                }
                                for user_id in watchlist_targets[sym]:
                                    await state.watchlist_websocket.broadcast(user_id, watch_payload)

        except Exception:
            await asyncio.sleep(3.0)
