from __future__ import annotations

import time
from dataclasses import dataclass
from redis.asyncio import Redis


@dataclass
class BucketSpec:
    capacity: int
    refill_per_sec: float


class RedisTokenBucketLimiter:
    def __init__(self, redis: Redis | None) -> None:
        self.redis = redis

    async def allow(self, key: str, spec: BucketSpec) -> bool:
        if self.redis is None:
            return True
        now = time.time()
        token_key = f"{key}:tokens"
        ts_key = f"{key}:ts"

        raw_tokens, raw_ts = await self.redis.mget(token_key, ts_key)
        tokens = float(raw_tokens) if raw_tokens is not None else float(spec.capacity)
        last = float(raw_ts) if raw_ts is not None else now

        elapsed = max(0.0, now - last)
        tokens = min(float(spec.capacity), tokens + elapsed * float(spec.refill_per_sec))
        allowed = tokens >= 1.0
        if allowed:
            tokens -= 1.0

        pipe = self.redis.pipeline()
        pipe.set(token_key, str(tokens), ex=300)
        pipe.set(ts_key, str(now), ex=300)
        await pipe.execute()
        return allowed
