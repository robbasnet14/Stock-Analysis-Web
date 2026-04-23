from __future__ import annotations

import json
from datetime import datetime
import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.news import NewsArticle
from app.services.stock_service import StockService


class EnsembleService:
    def __init__(self, stock_service: StockService) -> None:
        self.stock_service = stock_service

    @staticmethod
    def _clip01(value: float) -> float:
        return float(max(0.0, min(1.0, value)))

    async def _technical_model_score(self, db: AsyncSession, symbol: str) -> float:
        ti = await self.stock_service.get_latest_technical(db, symbol)
        if ti is None:
            return 0.5
        rsi = float(ti["rsi"])
        macd = float(ti["macd"])
        macd_signal = float(ti["macd_signal"])
        adx = float(ti["adx"])
        sma20 = float(ti["sma20"])
        sma50 = float(ti["sma50"])
        sma200 = float(ti["sma200"])
        rows = await self.stock_service.get_price_history(db, symbol, limit=3)
        px = float(rows[-1].price) if rows else sma20

        rsi_component = 1.0 - min(1.0, abs(rsi - 55.0) / 45.0)
        macd_component = 1.0 if macd > macd_signal else 0.0
        trend_component = float(np.mean([px > sma20, sma20 > sma50, sma50 > sma200]))
        adx_component = min(1.0, adx / 35.0)
        score = 0.35 * rsi_component + 0.25 * macd_component + 0.25 * trend_component + 0.15 * adx_component
        return self._clip01(score)

    async def _sentiment_model_score(self, db: AsyncSession, symbol: str) -> float:
        stmt = (
            select(NewsArticle)
            .where(NewsArticle.ticker == symbol.upper())
            .order_by(NewsArticle.published_at.desc())
            .limit(20)
        )
        news = list((await db.execute(stmt)).scalars().all())
        if not news:
            return 0.5
        sentiment = float(np.mean([float(n.sentiment_score) for n in news]))
        freq = min(1.0, len(news) / 20.0)
        score = 0.75 * ((sentiment + 1.0) / 2.0) + 0.25 * freq
        return self._clip01(score)

    async def _macro_model_score(self, db: AsyncSession, symbol: str, horizon: str) -> float:
        regime = await self.stock_service.get_market_regime(db)
        regime_name = regime.get("regime", "sideways")
        rows = await self.stock_service.get_price_history(db, symbol, limit=30)
        if len(rows) < 6:
            return 0.5
        ret_5 = ((rows[-1].price / rows[-6].price) - 1.0) * 100.0 if rows[-6].price else 0.0
        base = 0.5 + np.tanh(ret_5 / 8.0) * 0.25
        if regime_name == "bull":
            base += 0.1 if ret_5 > 0 else -0.05
        elif regime_name == "bear":
            base += -0.1 if ret_5 > 0 else 0.08
        if horizon == "long":
            base = 0.5 + (base - 0.5) * 0.7
        return self._clip01(float(base))

    async def get_ensemble_ranking(self, db: AsyncSession, tickers: list[str], horizon: str, redis_client=None) -> dict:
        horizon_key = (horizon or "short").strip().lower()
        if horizon_key not in {"short", "mid", "long"}:
            horizon_key = "short"

        cache_key = f"ensemble:ranking:{horizon_key}"
        if redis_client is not None:
            cached = await redis_client.get(cache_key)
            if cached:
                try:
                    return json.loads(cached)
                except Exception:
                    pass

        alpha_rows = await self.stock_service.get_alpha_ranking(db, tickers, horizon_key)
        factor_map = {row["symbol"]: float(row["alpha_score"]) for row in alpha_rows}
        symbols = list(factor_map.keys())

        items: list[dict] = []
        for symbol in symbols:
            factor_model = self._clip01(factor_map.get(symbol, 0.5))
            technical_model = await self._technical_model_score(db, symbol)
            sentiment_model = await self._sentiment_model_score(db, symbol)
            macro_model = await self._macro_model_score(db, symbol, horizon_key)
            final_score = (
                0.40 * factor_model
                + 0.30 * technical_model
                + 0.20 * sentiment_model
                + 0.10 * macro_model
            )
            items.append(
                {
                    "symbol": symbol,
                    "final_score": round(float(final_score), 4),
                    "models": {
                        "factor_model": round(factor_model, 4),
                        "technical_model": round(technical_model, 4),
                        "sentiment_model": round(sentiment_model, 4),
                        "macro_model": round(macro_model, 4),
                    },
                }
            )

        items.sort(key=lambda x: x["final_score"], reverse=True)
        payload = {"horizon": horizon_key, "as_of": datetime.utcnow().isoformat(), "items": items[:25]}
        if redis_client is not None:
            await redis_client.set(cache_key, json.dumps(payload), ex=300)
        return payload

    async def get_ensemble_diagnostics(self, db: AsyncSession, tickers: list[str], horizon: str, redis_client=None) -> dict:
        horizon_key = (horizon or "short").strip().lower()
        if horizon_key not in {"short", "mid", "long"}:
            horizon_key = "short"

        cache_key = f"ensemble:diagnostics:{horizon_key}"
        if redis_client is not None:
            cached = await redis_client.get(cache_key)
            if cached:
                try:
                    return json.loads(cached)
                except Exception:
                    pass

        ranking = await self.get_ensemble_ranking(db, tickers, horizon_key, redis_client=None)
        regime = await self.stock_service.get_market_regime(db)
        regime_conf = float(regime.get("confidence", 0.5))

        out: list[dict] = []
        for item in ranking["items"][:20]:
            models = item["models"]
            f = float(models["factor_model"])
            t = float(models["technical_model"])
            s = float(models["sentiment_model"])
            m = float(models["macro_model"])
            contributions = {
                "factor_model": round(0.40 * f, 4),
                "technical_model": round(0.30 * t, 4),
                "sentiment_model": round(0.20 * s, 4),
                "macro_model": round(0.10 * m, 4),
            }
            vec = np.array([f, t, s, m], dtype=float)
            disagreement = float(np.std(vec))
            confidence = max(0.05, min(0.95, 0.6 * (1.0 - disagreement) + 0.4 * regime_conf))
            center = float(item["final_score"])
            band = (1.0 - confidence) * 0.22
            lower = max(0.0, center - band)
            upper = min(1.0, center + band)
            out.append(
                {
                    "symbol": item["symbol"],
                    "final_score": round(center, 4),
                    "feature_contribution": contributions,
                    "confidence": round(confidence, 4),
                    "confidence_band": {
                        "low": round(lower, 4),
                        "base": round(center, 4),
                        "high": round(upper, 4),
                    },
                    "models": models,
                }
            )

        payload = {
            "horizon": horizon_key,
            "regime": regime,
            "as_of": datetime.utcnow().isoformat(),
            "items": out,
        }
        if redis_client is not None:
            await redis_client.set(cache_key, json.dumps(payload), ex=300)
        return payload
