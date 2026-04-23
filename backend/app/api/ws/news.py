from __future__ import annotations

import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.state import state


router = APIRouter(tags=["ws-news"])


@router.websocket("/ws/news")
async def ws_news(websocket: WebSocket):
    await websocket.accept()
    qp = websocket.query_params.get("tickers", "")
    tickers: set[str] = {x.strip().upper() for x in qp.split(",") if x.strip()}
    pubsub = None
    relay_task = None

    async def relay_loop() -> None:
        nonlocal pubsub
        if state.redis is None:
            return
        pubsub = state.redis.pubsub()
        channels = [f"news:{t}" for t in tickers] if tickers else []
        if channels:
            await pubsub.subscribe(*channels)
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if not msg:
                await asyncio.sleep(0.05)
                continue
            data = msg.get("data")
            if isinstance(data, bytes):
                data = data.decode("utf-8", "ignore")
            if isinstance(data, str):
                await websocket.send_text(data)

    try:
        if relay_task is None:
            relay_task = asyncio.create_task(relay_loop())
            await websocket.send_text(json.dumps({"type": "subscribed", "tickers": sorted(tickers)}))
        # First frame can include ticker subscriptions.
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except Exception:
                payload = {}
            incoming = payload.get("tickers")
            if isinstance(incoming, list):
                tickers = {str(t).upper() for t in incoming if str(t).strip()}
            elif isinstance(incoming, str) and incoming.strip():
                tickers = {x.strip().upper() for x in incoming.split(",") if x.strip()}
            if relay_task is None:
                relay_task = asyncio.create_task(relay_loop())
                await websocket.send_text(json.dumps({"type": "subscribed", "tickers": sorted(tickers)}))
            # keep-alive / updates
            if payload.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue
            if incoming is not None and relay_task is not None and state.redis is not None and pubsub is not None:
                await pubsub.unsubscribe()
                channels = [f"news:{t}" for t in tickers] if tickers else []
                if channels:
                    await pubsub.subscribe(*channels)
                await websocket.send_text(json.dumps({"type": "subscribed", "tickers": sorted(tickers)}))
    except WebSocketDisconnect:
        if relay_task is not None:
            relay_task.cancel()
        if pubsub is not None:
            await pubsub.aclose()
        return
