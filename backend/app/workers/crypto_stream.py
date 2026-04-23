import asyncio
import json
from datetime import datetime
from websockets import connect
from app.config import get_settings
from app.state import state


settings = get_settings()


def _parse_trade_payload(msg: dict) -> tuple[str, float, float, datetime] | None:
    stream = str(msg.get("stream", "")).lower()
    data = msg.get("data") or {}
    if "@trade" not in stream or not isinstance(data, dict):
        return None
    symbol = str(data.get("s", "")).upper()
    if not symbol:
        return None
    price = float(data.get("p") or 0.0)
    qty = float(data.get("q") or 0.0)
    ts_ms = int(data.get("T") or 0)
    if price <= 0:
        return None
    ts = datetime.utcfromtimestamp(ts_ms / 1000.0) if ts_ms else datetime.utcnow()
    mapping = {
        "BTCUSDT": "BTC-USD",
        "ETHUSDT": "ETH-USD",
    }
    ticker = mapping.get(symbol, symbol)
    return ticker, price, qty, ts


async def stream_crypto_forever() -> None:
    base_ws = (settings.binance_ws_url or "wss://stream.binance.com:9443/stream").rstrip("/")
    ws_url = f"{base_ws}?streams=btcusdt@trade/ethusdt@trade"
    while True:
        try:
            async with connect(ws_url, ping_interval=20, ping_timeout=20) as ws:
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=30.0)
                    try:
                        msg = json.loads(raw)
                    except Exception:
                        continue
                    parsed = _parse_trade_payload(msg)
                    if parsed is None:
                        continue
                    ticker, price, qty, ts = parsed
                    payload = {
                        "type": "tick",
                        "ticker": ticker,
                        "price": float(price),
                        "change_percent": 0.0,
                        "volume": float(qty),
                        "open_price": float(price),
                        "high_price": float(price),
                        "low_price": float(price),
                        "timestamp": ts.isoformat(),
                    }
                    if state.redis is not None:
                        await state.redis.set(f"price:{ticker}", str(price), ex=180)
                        await state.redis.set(f"latest:{ticker}", json.dumps(payload), ex=180)
                        await state.redis.publish(f"stream:{ticker}", json.dumps(payload))
                    await state.websocket.broadcast(ticker, payload)
        except Exception:
            await asyncio.sleep(3.0)
