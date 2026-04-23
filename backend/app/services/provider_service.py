from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import random


@dataclass
class FlowSnapshot:
    ticker: str
    dark_pool_volume: float
    unusual_options_score: float
    insider_bias_score: float
    provider: str


class FlowProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def fetch(self, ticker: str) -> FlowSnapshot:
        raise NotImplementedError


class PolygonFlowProvider(FlowProvider):
    name = "polygon-compatible"

    async def fetch(self, ticker: str) -> FlowSnapshot:
        return FlowSnapshot(
            ticker=ticker,
            dark_pool_volume=round(random.uniform(1_000_000, 20_000_000), 2),
            unusual_options_score=round(random.uniform(0.2, 0.95), 4),
            insider_bias_score=round(random.uniform(0.1, 0.8), 4),
            provider=self.name,
        )


class UnusualWhalesFlowProvider(FlowProvider):
    name = "unusualwhales-compatible"

    async def fetch(self, ticker: str) -> FlowSnapshot:
        return FlowSnapshot(
            ticker=ticker,
            dark_pool_volume=round(random.uniform(500_000, 12_000_000), 2),
            unusual_options_score=round(random.uniform(0.25, 0.99), 4),
            insider_bias_score=round(random.uniform(0.15, 0.9), 4),
            provider=self.name,
        )


class ProviderAggregator:
    def __init__(self) -> None:
        self.providers: list[FlowProvider] = [PolygonFlowProvider(), UnusualWhalesFlowProvider()]

    async def get_snapshot(self, ticker: str) -> dict:
        results = [await p.fetch(ticker.upper()) for p in self.providers]
        avg_dark_pool = sum(r.dark_pool_volume for r in results) / len(results)
        avg_options = sum(r.unusual_options_score for r in results) / len(results)
        avg_insider = sum(r.insider_bias_score for r in results) / len(results)

        return {
            "ticker": ticker.upper(),
            "dark_pool_volume": round(avg_dark_pool, 2),
            "unusual_options_score": round(avg_options, 4),
            "insider_bias_score": round(avg_insider, 4),
            "sources": [r.provider for r in results],
        }
