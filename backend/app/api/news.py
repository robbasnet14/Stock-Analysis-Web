from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.schemas.common import NewsItem
from app.services.news.aggregator import NewsAggregator
from app.config import get_settings
from app.state import state


router = APIRouter(prefix="/news", tags=["news"])
settings = get_settings()


async def _fetch_finnhub_on_demand(ticker: str) -> list[dict]:
    symbol = ticker.upper()
    cache_key = f"news:ondemand:{symbol}"
    if state.redis is not None:
        cached = await state.redis.get(cache_key)
        if cached:
            return []
        await state.redis.setex(cache_key, settings.news_ondemand_fetch_ttl, "1")
    agg = NewsAggregator()
    try:
        return await agg.fetch_finnhub(symbol)
    finally:
        await agg.close()


@router.get("/{ticker}")
async def get_news(ticker: str, db: AsyncSession = Depends(get_db)) -> dict:
    rows = await state.news_service.get_latest_news(db, ticker)

    if not rows:
        try:
            fetched = await _fetch_finnhub_on_demand(ticker)
            if not fetched:
                fetched = await state.news_service.fetch_news(ticker)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Live news unavailable: {exc}") from exc
        await state.news_service.save_articles(db, fetched)
        rows = await state.news_service.get_latest_news(db, ticker)
    else:
        try:
            latest = max((r.published_at for r in rows if r.published_at), default=None)
            if latest is None or (datetime.now(timezone.utc) - latest.replace(tzinfo=timezone.utc)).total_seconds() > settings.news_ondemand_fetch_ttl:
                fetched = await _fetch_finnhub_on_demand(ticker)
                if fetched:
                    await state.news_service.save_articles(db, fetched)
                    rows = await state.news_service.get_latest_news(db, ticker)
        except Exception:
            pass

    # Top-up path: if DB has too few rows for this ticker, pull RSS sources immediately.
    if len(rows) < 5:
        agg = NewsAggregator()
        try:
            extra = []
            try:
                extra.extend(await agg.fetch_yahoo(ticker))
            except Exception:
                pass
            try:
                extra.extend(await agg.fetch_google_news(ticker))
            except Exception:
                pass

            mapped = []
            symbol = ticker.upper()
            for item in extra:
                headline = str(item.get("title") or "").strip()
                if not headline:
                    continue
                summary = str(item.get("summary") or "").strip()
                sentiment_label, sentiment_score = state.news_service.analyze_sentiment(f"{headline}. {summary}")
                mapped.append(
                    {
                        "ticker": symbol,
                        "headline": headline,
                        "summary": summary,
                        "source": str(item.get("source") or "rss"),
                        "url": str(item.get("url") or ""),
                        "sentiment_label": sentiment_label,
                        "sentiment_score": sentiment_score,
                        "published_at": item.get("published_at"),
                    }
                )
            if mapped:
                await state.news_service.save_articles(db, mapped)
                rows = await state.news_service.get_latest_news(db, ticker)
        finally:
            await agg.close()

    items = [
        NewsItem(
            ticker=r.ticker,
            headline=r.headline,
            summary=r.summary,
            source=r.source,
            url=r.url,
            sentiment_label=r.sentiment_label,
            sentiment_score=r.sentiment_score,
            published_at=r.published_at,
        )
        for r in rows
    ]

    avg_sentiment = 0.0
    if items:
        avg_sentiment = sum(i.sentiment_score for i in items) / len(items)

    return {
        "ticker": ticker.upper(),
        "average_sentiment": round(avg_sentiment, 4),
        "articles": items,
    }
