from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.state import state


router = APIRouter(tags=["ws-prices"])


@router.websocket("/ws/prices/{ticker}")
async def ws_prices(websocket: WebSocket, ticker: str):
    symbol = ticker.upper()
    await state.websocket.connect(symbol, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        state.websocket.disconnect(symbol, websocket)
