from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any


class MarketDataProvider(ABC):
    name: str

    @abstractmethod
    async def quote(self, symbol: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    async def candles(self, symbol: str, start: datetime, end: datetime, timeframe: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def search(self, query: str) -> list[dict[str, Any]]:
        return []

    async def symbols(self) -> list[dict[str, Any]]:
        return []

    async def news(self, symbol: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        return []

    async def close(self) -> None:
        return None
