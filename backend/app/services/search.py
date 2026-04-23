from __future__ import annotations

from app.services.market_data import MarketDataService


class SearchService:
    def __init__(self, market_data: MarketDataService) -> None:
        self.market_data = market_data

    async def autocomplete(self, query: str) -> list[dict]:
        q = (query or "").strip()
        if len(q) < 1:
            return []
        return await self.market_data.search(q)
