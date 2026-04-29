from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news import NewsArticle


THEME_KEYWORDS = {
    "ai": ["artificial intelligence", "ai", "llm", "chatgpt", "claude", "gemini", "machine learning", "neural"],
    "semis": ["semiconductor", "chip", "wafer", "fab", "gpu", "tsmc", "asml"],
    "ev": ["electric vehicle", "ev", "battery", "lithium", "tesla", "rivian"],
    "biotech": ["biotech", "fda approval", "clinical trial", "drug", "phase 3"],
    "macro": ["fed", "interest rate", "inflation", "cpi", "jobs report", "gdp"],
    "regulation": ["regulation", "antitrust", "lawsuit", "sec", "ftc", "investigation"],
    "earnings_season": ["earnings", "q1", "q2", "q3", "q4", "beat estimates", "missed"],
    "geopolitics": ["china", "russia", "tariff", "sanction", "war", "election"],
}


async def detect_themes(*, db: AsyncSession, redis_client=None, window_hours: int = 24) -> dict[str, Any]:
    """Score simple keyword themes by article count, recency, sentiment, and ticker mentions."""
    cache_key = f"themes:{int(window_hours)}h:v2"
    if redis_client is not None:
        cached = await redis_client.get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass

    now = datetime.utcnow()
    cutoff = now - timedelta(hours=window_hours)
    stmt = select(NewsArticle).where(NewsArticle.published_at >= cutoff).order_by(NewsArticle.published_at.desc()).limit(1000)
    articles = list((await db.execute(stmt)).scalars().all())

    theme_scores: dict[str, Any] = {}
    for theme, keywords in THEME_KEYWORDS.items():
        matched = []
        for article in articles:
            text = f"{article.title or ''} {article.headline or ''} {article.summary or ''}".lower()
            if any(k in text for k in keywords):
                matched.append(article)
        if not matched:
            continue

        avg_sentiment = sum(float(a.sentiment_score or 0.0) for a in matched) / len(matched)
        strength = 0.0
        tickers: set[str] = set()
        for article in matched:
            published = article.published_at or now
            age_hours = max(1.0, (now - published.replace(tzinfo=None)).total_seconds() / 3600.0)
            strength += 1.0 / age_hours
            if article.ticker:
                tickers.add(str(article.ticker).upper())

        theme_scores[theme] = {
            "article_count": len(matched),
            "avg_sentiment": round(avg_sentiment, 3),
            "strength": round(strength, 2),
            "trending": strength > 5,
            "tickers_mentioned": sorted(tickers)[:20],
        }

    hot = [item for item in sorted(theme_scores.items(), key=lambda kv: float(kv[1]["strength"]), reverse=True) if bool(item[1].get("trending"))][:5]
    result = {
        "themes": theme_scores,
        "hot_themes": [name for name, _ in hot],
        "computed_at": now.isoformat(),
    }
    if redis_client is not None:
        await redis_client.setex(cache_key, 1800, json.dumps(result))
    return result


def theme_modifier_for_ticker(ticker: str, themes: dict[str, Any]) -> dict[str, Any]:
    symbol = ticker.upper()
    boost = 0.0
    matched_themes: list[dict[str, Any]] = []
    for theme_name, theme in (themes.get("themes") or {}).items():
        tickers = [str(t).upper() for t in theme.get("tickers_mentioned") or []]
        if symbol in tickers and bool(theme.get("trending")):
            sentiment = float(theme.get("avg_sentiment") or 0.0)
            boost += 0.10 * sentiment
            matched_themes.append({"theme": theme_name, "sentiment": round(sentiment, 3)})
    return {
        "modifier": 1.0 + boost,
        "matched_themes": matched_themes,
        "explanation": f"Tagged in trending themes: {', '.join(t['theme'] for t in matched_themes)}" if matched_themes else None,
    }
