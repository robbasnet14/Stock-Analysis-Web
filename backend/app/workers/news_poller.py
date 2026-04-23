import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.config import get_settings
from app.db.database import SessionLocal
from app.models.news import NewsArticle
from app.models.news_article_ticker import NewsArticleTicker
from app.models.watchlist import WatchlistItem
from app.services.news.aggregator import NewsAggregator
from app.services.news.dedup import Deduper
from app.services.news.sentiment import NewsSentimentService
from app.state import state


settings = get_settings()


async def _watchlist_tickers(db) -> list[str]:
    rows = [r.symbol for r in (await db.execute(select(WatchlistItem))).scalars().all()]
    if rows:
        return sorted(set([str(x).upper() for x in rows if x]))
    if state.watchlist:
        return sorted(set(state.watchlist))
    return settings.ticker_list


async def _save_articles(db, redis_client, rows: list[dict[str, Any]]) -> int:
    inserted = 0
    for row in rows:
        ticker = str(row.get("ticker") or "").upper()
        if not ticker:
            continue
        url_hash = str(row.get("url_hash") or "")
        title_hash = str(row.get("title_hash") or "")
        exists_stmt = select(NewsArticle.id).where(NewsArticle.ticker == ticker, NewsArticle.url_hash == url_hash).limit(1)
        exists = (await db.execute(exists_stmt)).scalar_one_or_none()
        if exists:
            continue
        article = NewsArticle(
            ticker=ticker,
            headline=str(row.get("title") or "")[:512],
            title=str(row.get("title") or ""),
            summary=str(row.get("summary") or ""),
            source=str(row.get("source") or "unknown")[:128],
            url=str(row.get("url") or "")[:1024],
            url_hash=url_hash,
            title_hash=title_hash,
            dedupe_key=f"{ticker}:{url_hash or title_hash}",
            sentiment_label=str(row.get("sentiment_label") or "neutral"),
            sentiment=str(row.get("sentiment_label") or "neutral"),
            sentiment_score=float(row.get("sentiment_score") or 0.0),
            sentiment_model=str(row.get("sentiment_model") or "vader"),
            published_at=row.get("published_at") or datetime.now(timezone.utc),
            ingested_at=datetime.now(timezone.utc),
        )
        db.add(article)
        await db.flush()
        db.add(NewsArticleTicker(article_id=article.id, ticker=ticker))
        inserted += 1

        if redis_client is not None:
            payload = {
                "ticker": ticker,
                "headline": article.headline,
                "summary": article.summary,
                "source": article.source,
                "url": article.url,
                "sentiment_label": article.sentiment_label,
                "sentiment_score": article.sentiment_score,
                "published_at": article.published_at.isoformat(),
            }
            await redis_client.publish(f"news:{ticker}", json.dumps(payload))

    if inserted:
        await db.commit()
    return inserted


async def poll_news_forever() -> None:
    aggregator = NewsAggregator()
    deduper = Deduper()
    sentiment = NewsSentimentService()
    last_yahoo = 0.0
    last_google = 0.0
    last_marketaux = 0.0
    last_alpha = 0.0

    try:
        while True:
            now_ts = asyncio.get_event_loop().time()
            async with SessionLocal() as db:
                tickers = await _watchlist_tickers(db)
                # Finnhub per ticker every 30s.
                for t in tickers:
                    try:
                        rows = await aggregator.fetch_finnhub(t)
                    except Exception:
                        rows = []
                    rows = await sentiment.score_articles(rows, redis_client=state.redis)
                    cleaned: list[dict[str, Any]] = []
                    for r in rows:
                        check = await deduper.check(state.redis, url=str(r.get("url") or ""), title=str(r.get("title") or ""))
                        if check.is_duplicate:
                            continue
                        r["url_hash"] = check.url_hash
                        r["title_hash"] = check.title_hash
                        cleaned.append(r)
                    await _save_articles(db, state.redis, cleaned)

                if now_ts - last_yahoo >= 60.0:
                    last_yahoo = now_ts
                    for t in tickers:
                        try:
                            rows = await aggregator.fetch_yahoo(t)
                        except Exception:
                            rows = []
                        rows = await sentiment.score_articles(rows, redis_client=state.redis)
                        cleaned = []
                        for r in rows:
                            check = await deduper.check(state.redis, url=str(r.get("url") or ""), title=str(r.get("title") or ""))
                            if check.is_duplicate:
                                continue
                            r["url_hash"] = check.url_hash
                            r["title_hash"] = check.title_hash
                            cleaned.append(r)
                        await _save_articles(db, state.redis, cleaned)

                if now_ts - last_google >= 60.0:
                    last_google = now_ts
                    for t in tickers:
                        try:
                            rows = await aggregator.fetch_google_news(t)
                        except Exception:
                            rows = []
                        rows = await sentiment.score_articles(rows, redis_client=state.redis)
                        cleaned = []
                        for r in rows:
                            check = await deduper.check(state.redis, url=str(r.get("url") or ""), title=str(r.get("title") or ""))
                            if check.is_duplicate:
                                continue
                            r["url_hash"] = check.url_hash
                            r["title_hash"] = check.title_hash
                            cleaned.append(r)
                        await _save_articles(db, state.redis, cleaned)

                if now_ts - last_marketaux >= 900.0:
                    last_marketaux = now_ts
                    try:
                        rows = await aggregator.fetch_marketaux(tickers[:3])
                    except Exception:
                        rows = []
                    rows = await sentiment.score_articles(rows, redis_client=state.redis)
                    cleaned = []
                    for r in rows:
                        check = await deduper.check(state.redis, url=str(r.get("url") or ""), title=str(r.get("title") or ""))
                        if check.is_duplicate:
                            continue
                        r["url_hash"] = check.url_hash
                        r["title_hash"] = check.title_hash
                        cleaned.append(r)
                    await _save_articles(db, state.redis, cleaned)

                if now_ts - last_alpha >= 3600.0:
                    last_alpha = now_ts
                    try:
                        rows = await aggregator.fetch_alpha_vantage_news(tickers[:3])
                    except Exception:
                        rows = []
                    rows = await sentiment.score_articles(rows, redis_client=state.redis)
                    cleaned = []
                    for r in rows:
                        check = await deduper.check(state.redis, url=str(r.get("url") or ""), title=str(r.get("title") or ""))
                        if check.is_duplicate:
                            continue
                        r["url_hash"] = check.url_hash
                        r["title_hash"] = check.title_hash
                        cleaned.append(r)
                    await _save_articles(db, state.redis, cleaned)

            await asyncio.sleep(30)
    finally:
        await aggregator.close()
        await sentiment.close()

