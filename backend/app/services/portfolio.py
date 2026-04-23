from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PositionCalc:
    ticker: str
    quantity: float
    avg_cost: float
    live_price: float

    @property
    def market_value(self) -> float:
        return self.quantity * self.live_price

    @property
    def cost_basis(self) -> float:
        return self.quantity * self.avg_cost

    @property
    def pnl(self) -> float:
        return self.market_value - self.cost_basis


def summarize_positions(rows: list[PositionCalc]) -> dict:
    mv = sum(r.market_value for r in rows)
    cb = sum(r.cost_basis for r in rows)
    pnl = mv - cb
    pct = (pnl / cb * 100.0) if cb > 0 else 0.0
    return {"market_value": mv, "cost_basis": cb, "pnl": pnl, "pnl_percent": pct}
