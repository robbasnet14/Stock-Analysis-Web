from __future__ import annotations

import json
from typing import Any
from redis.asyncio import Redis


class RedisCache:
    def __init__(self, redis: Redis | None) -> None:
        self.redis = redis

    async def get_json(self, key: str) -> Any:
        if self.redis is None:
            return None
        raw = await self.redis.get(key)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    async def set_json(self, key: str, value: Any, ttl: int = 60) -> None:
        if self.redis is None:
            return
        await self.redis.set(key, json.dumps(value, default=str), ex=max(1, int(ttl)))
