import json
from collections import defaultdict
from fastapi import WebSocket


class WebSocketManager:
    def __init__(self) -> None:
        self.connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, ticker: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections[ticker].add(websocket)

    def disconnect(self, ticker: str, websocket: WebSocket) -> None:
        if ticker in self.connections:
            self.connections[ticker].discard(websocket)
            if not self.connections[ticker]:
                self.connections.pop(ticker, None)

    async def broadcast(self, ticker: str, payload: dict) -> None:
        dead: list[WebSocket] = []
        for ws in self.connections.get(ticker, set()):
            try:
                await ws.send_text(json.dumps(payload, default=str))
            except Exception:
                dead.append(ws)

        for ws in dead:
            self.disconnect(ticker, ws)
