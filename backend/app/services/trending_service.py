from __future__ import annotations

import json
from datetime import datetime, timedelta
import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.news import NewsArticle
from app.services.stock_service import StockService


class TrendingService:
    def __init__(self, stock_service: StockService) -> None:
        self.stock_service = stock_service

    async def get_trending(self, db: AsyncSession, tickers: list[str], redis_client=None) -> dict:
        cache_key = "market:trending:v1"
        if redis_client is not None:
            cached = await redis_client.get(cache_key)
            if cached:
                try:
                    return json.loads(cached)
                except Exception:
                    pass

        rows: list[dict] = []
        since = datetime.utcnow() - timedelta(days=7)
        for ticker in sorted(set(tickers))[:150]:
            prices = await self.stock_service.get_price_history(db, ticker, limit=40)
            if len(prices) < 31:
                continue
            p_now = float(prices[-1].price)
            p_prev = float(prices[-2].price)
            momentum_1d = ((p_now / p_prev) - 1.0) * 100.0 if p_prev else 0.0
            vols = [float(r.volume) for r in prices[-31:]]
            avg30 = float(np.mean(vols[:-1])) if len(vols) > 1 else float(np.mean(vols))
            volume_spike = (vols[-1] / avg30) if avg30 > 0 else 1.0

            news_stmt = (
                select(NewsArticle)
                .where(NewsArticle.ticker == ticker.upper(), NewsArticle.published_at >= since)
                .order_by(NewsArticle.published_at.desc())
                .limit(50)
            )
            news = list((await db.execute(news_stmt)).scalars().all())
            news_freq = len(news)
            sentiment = float(np.mean([float(n.sentiment_score) for n in news])) if news else 0.0

            trending_score = (
                0.35 * np.tanh((volume_spike - 1.0) / 1.5)
                + 0.30 * np.tanh(momentum_1d / 4.0)
                + 0.20 * min(1.0, news_freq / 20.0)
                + 0.15 * np.tanh(sentiment * 1.8)
            )
            rows.append(
                {
                    "symbol": ticker.upper(),
                    "trending_score": round(float((trending_score + 1.0) / 2.0), 4),
                    "factors": {
                        "volume_spike": round(volume_spike, 4),
                        "momentum_1d": round(momentum_1d, 4),
                        "news_frequency": float(news_freq),
                        "sentiment_score": round(sentiment, 4),
                    },
                }
            )

        rows.sort(key=lambda x: x["trending_score"], reverse=True)
        payload = {"as_of": datetime.utcnow().isoformat(), "items": rows[:20]}
        if redis_client is not None:
            await redis_client.set(cache_key, json.dumps(payload), ex=300)
        return payload
