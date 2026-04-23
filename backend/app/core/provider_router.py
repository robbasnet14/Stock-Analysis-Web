from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


@dataclass
class ProviderHealth:
    configured: bool
    successes: int = 0
    failures: int = 0
    consecutive_failures: int = 0
    last_ok: str | None = None
    last_error: str | None = None
    breaker_until: str | None = None


class ProviderRouter:
    def __init__(self) -> None:
        self.health: dict[str, ProviderHealth] = {}

    def register(self, provider_name: str, configured: bool) -> None:
        self.health.setdefault(provider_name, ProviderHealth(configured=configured))

    def can_try(self, provider_name: str) -> bool:
        row = self.health.get(provider_name)
        if row is None:
            return True
        if not row.breaker_until:
            return True
        try:
            until = datetime.fromisoformat(row.breaker_until)
        except Exception:
            row.breaker_until = None
            return True
        return datetime.utcnow() >= until

    def record_success(self, provider_name: str) -> None:
        row = self.health.setdefault(provider_name, ProviderHealth(configured=False))
        row.successes += 1
        row.consecutive_failures = 0
        row.last_ok = datetime.utcnow().isoformat()
        row.last_error = None
        row.breaker_until = None

    def record_failure(
        self,
        provider_name: str,
        error: str,
        cooldown_s: int = 0,
        *,
        trip_breaker: bool = True,
    ) -> None:
        row = self.health.setdefault(provider_name, ProviderHealth(configured=False))
        row.failures += 1
        row.last_error = (error or "unknown error")[:400]
        if not trip_breaker:
            return
        row.consecutive_failures += 1
        if cooldown_s > 0:
            row.breaker_until = (datetime.utcnow() + timedelta(seconds=max(1, cooldown_s))).isoformat()

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {
            k: {
                "configured": v.configured,
                "successes": v.successes,
                "failures": v.failures,
                "consecutive_failures": v.consecutive_failures,
                "last_ok": v.last_ok,
                "last_error": v.last_error,
                "breaker_until": v.breaker_until,
            }
            for k, v in self.health.items()
        }
