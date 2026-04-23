import json
from collections import defaultdict
from fastapi import WebSocket


class OrderWebSocketManager:
    def __init__(self) -> None:
        self.connections: dict[int, set[WebSocket]] = defaultdict(set)

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections[user_id].add(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        if user_id in self.connections:
            self.connections[user_id].discard(websocket)
            if not self.connections[user_id]:
                self.connections.pop(user_id, None)

    async def broadcast(self, user_id: int, payload: dict) -> None:
        dead: list[WebSocket] = []
        for ws in self.connections.get(user_id, set()):
            try:
                await ws.send_text(json.dumps(payload, default=str))
            except Exception:
                dead.append(ws)

        for ws in dead:
            self.disconnect(user_id, ws)
