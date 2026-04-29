from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket
from jose import JWTError

from app.db.database import SessionLocal
from app.models.user import User
from app.services.auth_service import decode_token
from app.state import state


router = APIRouter()


@router.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket, token: str | None = None):
    if not token:
        await websocket.close(code=1008)
        return
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise ValueError("wrong token")
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        await websocket.close(code=1008)
        return

    async with SessionLocal() as db:
        user = await db.get(User, user_id)
        if user is None:
            await websocket.close(code=1008)
            return

    await websocket.accept()
    if state.redis is None:
        await websocket.close(code=1011)
        return

    pubsub = state.redis.pubsub()
    await pubsub.subscribe(f"alerts:{user_id}")
    try:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            data = message.get("data")
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            try:
                await websocket.send_json(json.loads(data))
            except Exception:
                await websocket.send_text(str(data))
    finally:
        await pubsub.unsubscribe(f"alerts:{user_id}")
        await pubsub.close()
