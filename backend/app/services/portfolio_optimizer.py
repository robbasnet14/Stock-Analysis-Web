from __future__ import annotations

import numpy as np
from scipy.optimize import minimize
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.stock_service import StockService


class PortfolioOptimizerService:
    def __init__(self, stock_service: StockService) -> None:
        self.stock_service = stock_service

    async def optimize(self, db: AsyncSession, symbols: list[str]) -> dict:
        unique = [s.upper() for s in symbols if s]
        unique = list(dict.fromkeys(unique))
        if len(unique) < 2:
            raise ValueError("at least two symbols are required")

        returns_map: dict[str, np.ndarray] = {}
        for symbol in unique:
            rows = await self.stock_service.get_price_history(db, symbol, limit=260)
            if len(rows) < 80:
                continue
            close = np.array([float(r.price) for r in rows], dtype=float)
            rets = np.diff(np.log(np.clip(close, 1e-9, None)))
            if len(rets) >= 60:
                returns_map[symbol] = rets[-252:] if len(rets) > 252 else rets

        usable = list(returns_map.keys())
        if len(usable) < 2:
            raise ValueError("not enough historical data for optimization")

        min_len = min(len(returns_map[s]) for s in usable)
        matrix = np.column_stack([returns_map[s][-min_len:] for s in usable])
        mean_daily = np.mean(matrix, axis=0)
        cov_daily = np.cov(matrix, rowvar=False)

        annual_return = mean_daily * 252.0
        annual_cov = cov_daily * 252.0
        risk_free = 0.03

        n = len(usable)
        init = np.full(n, 1.0 / n)
        bounds = [(0.0, 1.0) for _ in range(n)]
        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

        def objective(w: np.ndarray) -> float:
            p_ret = float(np.dot(w, annual_return))
            p_vol = float(np.sqrt(np.clip(np.dot(w.T, np.dot(annual_cov, w)), 1e-12, None)))
            sharpe = (p_ret - risk_free) / p_vol if p_vol > 0 else -1e9
            return -sharpe

        res = minimize(objective, init, method="SLSQP", bounds=bounds, constraints=constraints)
        weights = res.x if res.success else init
        p_return = float(np.dot(weights, annual_return))
        p_vol = float(np.sqrt(np.clip(np.dot(weights.T, np.dot(annual_cov, weights)), 1e-12, None)))
        sharpe = (p_return - risk_free) / p_vol if p_vol > 0 else 0.0

        out_weights = {symbol: round(float(weight), 4) for symbol, weight in zip(usable, weights)}
        return {
            "recommended_weights": out_weights,
            "expected_return": round(p_return, 4),
            "portfolio_volatility": round(p_vol, 4),
            "sharpe_ratio": round(float(sharpe), 4),
        }
