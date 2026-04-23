from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.models.news import NewsArticle
from app.schemas.common import PredictionOut
from app.state import state


router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.get("/{ticker}", response_model=PredictionOut)
async def get_prediction(ticker: str, db: AsyncSession = Depends(get_db)) -> PredictionOut:
    latest = await state.ml_service.latest_prediction(db, ticker)
    if latest is None:
        latest = await state.ml_service.predict(db, ticker)

    return PredictionOut(**latest)


@router.get("/{ticker}/explanation")
async def prediction_explanation(ticker: str, db: AsyncSession = Depends(get_db)) -> dict:
    latest = await state.ml_service.latest_prediction(db, ticker)
    if latest is None:
        latest = await state.ml_service.predict(db, ticker)

    bull = latest["bull_probability"]
    tone = "bullish" if bull >= 0.6 else "bearish" if bull <= 0.4 else "mixed"

    explanation = (
        f"{ticker.upper()} currently looks {tone}. "
        f"Bull probability is {round(bull * 100, 1)}%. "
        f"The strongest drivers are: {', '.join(latest['reasons'])}."
    )

    return {
        "ticker": ticker.upper(),
        "bull_probability": latest["bull_probability"],
        "bear_probability": latest["bear_probability"],
        "explanation": explanation,
        "reasons": latest["reasons"],
    }


@router.get("/{ticker}/llm-explanation")
async def prediction_llm_explanation(
    ticker: str,
    horizon: str = "short",
    db: AsyncSession = Depends(get_db),
) -> dict:
    symbol = ticker.upper()
    latest = await state.ml_service.latest_prediction(db, symbol)
    if latest is None:
        latest = await state.ml_service.predict(db, symbol)

    stock_rows = await state.stock_service.get_price_history(db, symbol, limit=32)
    momentum_pct = 0.0
    volume_ratio = 1.0
    if len(stock_rows) >= 8:
        latest_row = stock_rows[-1]
        lookback = stock_rows[-8]
        momentum_pct = ((latest_row.price / lookback.price) - 1.0) * 100.0 if lookback.price else 0.0
        volumes = [float(r.volume) for r in stock_rows[-8:]]
        avg_vol = (sum(volumes[:-1]) / max(1, len(volumes) - 1)) if volumes else 0.0
        volume_ratio = (volumes[-1] / avg_vol) if avg_vol > 0 else 1.0

    news_stmt = (
        select(NewsArticle)
        .where(NewsArticle.ticker == symbol)
        .order_by(NewsArticle.published_at.desc())
        .limit(10)
    )
    news_rows = list((await db.execute(news_stmt)).scalars().all())
    sentiment = (sum(float(n.sentiment_score) for n in news_rows) / len(news_rows)) if news_rows else 0.0

    explanation = await state.llm_service.explain_stock(
        ticker=symbol,
        horizon=horizon,
        bull_probability=float(latest["bull_probability"]),
        reasons=list(latest["reasons"]),
        sentiment=float(sentiment),
        momentum_pct=float(momentum_pct),
        volume_ratio=float(volume_ratio),
    )

    return {
        "ticker": symbol,
        "horizon": horizon.lower(),
        "bull_probability": latest["bull_probability"],
        "bear_probability": latest["bear_probability"],
        "reasons": latest["reasons"],
        "sentiment": round(sentiment, 4),
        "momentum_percent": round(momentum_pct, 4),
        "volume_ratio": round(volume_ratio, 4),
        "explanation": explanation,
    }
