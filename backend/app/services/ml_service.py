from __future__ import annotations

import json
from datetime import datetime
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.news import NewsArticle
from app.models.prediction import Prediction
from app.models.stock import StockPrice
from app.utils.ta import compute_rsi


class MLService:
    FEATURE_COLUMNS = ["ma_fast", "ma_slow", "momentum", "volume_change", "rsi"]

    def __init__(self) -> None:
        self.model = RandomForestClassifier(n_estimators=150, random_state=42)
        self.scaler = StandardScaler()
        self.is_trained = False
        self.model_version = "rf-v1"

    async def train(self, db: AsyncSession, ticker: str) -> None:
        stmt = (
            select(StockPrice)
            .where(StockPrice.ticker == ticker.upper())
            .order_by(StockPrice.timestamp.asc())
            .limit(500)
        )
        rows = list((await db.execute(stmt)).scalars().all())

        if len(rows) < 60:
            return

        frame = pd.DataFrame(
            [
                {
                    "price": r.price,
                    "volume": r.volume,
                    "timestamp": r.timestamp,
                }
                for r in rows
            ]
        )
        frame["ma_fast"] = frame["price"].rolling(5).mean()
        frame["ma_slow"] = frame["price"].rolling(20).mean()
        frame["momentum"] = frame["price"].pct_change(5)
        frame["volume_change"] = frame["volume"].pct_change().replace([np.inf, -np.inf], 0)
        frame["rsi"] = compute_rsi(frame["price"])
        frame["target"] = (frame["price"].shift(-3) > frame["price"]).astype(int)
        frame = frame.dropna()

        if len(frame) < 30:
            return

        x = frame[self.FEATURE_COLUMNS]
        y = frame["target"]

        x_scaled = self.scaler.fit_transform(x)
        self.model.fit(x_scaled, y)
        self.is_trained = True

    async def predict(self, db: AsyncSession, ticker: str) -> dict:
        ticker = ticker.upper()

        if not self.is_trained:
            await self.train(db, ticker)

        stock_stmt = (
            select(StockPrice)
            .where(StockPrice.ticker == ticker)
            .order_by(StockPrice.timestamp.asc())
            .limit(120)
        )
        rows = list((await db.execute(stock_stmt)).scalars().all())

        if len(rows) < 25:
            return {
                "ticker": ticker,
                "bull_probability": 0.5,
                "bear_probability": 0.5,
                "reasons": ["insufficient data to train model yet"],
                "generated_at": datetime.utcnow(),
            }

        frame = pd.DataFrame([{"price": r.price, "volume": r.volume} for r in rows])
        frame["ma_fast"] = frame["price"].rolling(5).mean()
        frame["ma_slow"] = frame["price"].rolling(20).mean()
        frame["momentum"] = frame["price"].pct_change(5)
        frame["volume_change"] = frame["volume"].pct_change().replace([np.inf, -np.inf], 0)
        frame["rsi"] = compute_rsi(frame["price"])
        frame = frame.dropna()

        latest = frame.iloc[-1]

        news_stmt = (
            select(NewsArticle)
            .where(NewsArticle.ticker == ticker)
            .order_by(NewsArticle.published_at.desc())
            .limit(10)
        )
        news = list((await db.execute(news_stmt)).scalars().all())
        sentiment = np.mean([n.sentiment_score for n in news]) if news else 0

        features = pd.DataFrame(
            [
                {
                    "ma_fast": latest["ma_fast"],
                    "ma_slow": latest["ma_slow"],
                    "momentum": latest["momentum"],
                    "volume_change": latest["volume_change"],
                    "rsi": latest["rsi"],
                }
            ],
            columns=self.FEATURE_COLUMNS,
        )

        bull_prob = 0.5
        if self.is_trained:
            bull_prob = float(self.model.predict_proba(self.scaler.transform(features))[0][1])

        bull_prob = float(np.clip(bull_prob + sentiment * 0.08, 0.01, 0.99))
        bear_prob = float(1 - bull_prob)

        reasons: list[str] = []
        if sentiment > 0.1:
            reasons.append("positive news sentiment")
        elif sentiment < -0.1:
            reasons.append("negative news sentiment")

        if latest["rsi"] < 35:
            reasons.append("RSI bounce setup")
        elif latest["rsi"] > 70:
            reasons.append("RSI overbought risk")

        if latest["volume_change"] > 0.15:
            reasons.append("volume spike")

        if latest["ma_fast"] > latest["ma_slow"]:
            reasons.append("short MA above long MA")

        if not reasons:
            reasons.append("mixed indicators")

        output = {
            "ticker": ticker,
            "bull_probability": round(bull_prob, 4),
            "bear_probability": round(bear_prob, 4),
            "reasons": reasons,
            "generated_at": datetime.utcnow(),
        }

        pred = Prediction(
            ticker=ticker,
            bull_probability=output["bull_probability"],
            bear_probability=output["bear_probability"],
            reasons=json.dumps(reasons),
            model_version=self.model_version,
            generated_at=output["generated_at"],
        )
        db.add(pred)
        await db.commit()
        return output

    async def latest_prediction(self, db: AsyncSession, ticker: str) -> dict | None:
        stmt = (
            select(Prediction)
            .where(Prediction.ticker == ticker.upper())
            .order_by(Prediction.generated_at.desc())
            .limit(1)
        )
        row = (await db.execute(stmt)).scalar_one_or_none()
        if not row:
            return None

        return {
            "ticker": row.ticker,
            "bull_probability": row.bull_probability,
            "bear_probability": row.bear_probability,
            "reasons": json.loads(row.reasons or "[]"),
            "generated_at": row.generated_at,
        }
