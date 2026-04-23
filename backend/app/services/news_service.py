from datetime import datetime, timedelta, timezone
import hashlib
import re
import httpx
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.models.news import NewsArticle


settings = get_settings()


class NewsService:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(timeout=20.0)
        self._sentiment_pipe = None
        self.provider_health: dict[str, dict] = {
            "finnhub_news": self._new_provider_health(bool(settings.finnhub_api_key)),
        }

    @staticmethod
    def _new_provider_health(configured: bool) -> dict:
        return {
            "configured": configured,
            "last_ok": None,
            "last_error": None,
            "last_latency_ms": None,
            "last_checked": None,
            "successes": 0,
            "failures": 0,
        }

    def _record_provider(self, provider: str, ok: bool, *, latency_ms: float | None = None, error: str | None = None) -> None:
        row = self.provider_health.setdefault(provider, self._new_provider_health(False))
        row["last_checked"] = datetime.utcnow().isoformat()
        if latency_ms is not None:
            row["last_latency_ms"] = round(float(latency_ms), 2)
        if ok:
            row["successes"] = int(row.get("successes", 0)) + 1
            row["last_ok"] = datetime.utcnow().isoformat()
            row["last_error"] = None
        else:
            row["failures"] = int(row.get("failures", 0)) + 1
            row["last_error"] = str(error or "unknown error")[:400]

    def get_provider_health(self) -> dict[str, dict]:
        return {k: dict(v) for k, v in self.provider_health.items()}

    async def close(self) -> None:
        await self.client.aclose()

    @property
    def sentiment_pipe(self):
        if self._sentiment_pipe is None:
            try:
                from transformers import pipeline
                self._sentiment_pipe = pipeline("sentiment-analysis", model="distilbert/distilbert-base-uncased-finetuned-sst-2-english")
            except Exception:
                self._sentiment_pipe = "fallback"
        return self._sentiment_pipe

    def analyze_sentiment(self, text: str) -> tuple[str, float]:
        text = (text or "").strip()
        if not text:
            return "neutral", 0.0

        if self.sentiment_pipe == "fallback":
            pos_words = ["growth", "beat", "record", "surge", "upgrade", "strong", "bull"]
            neg_words = ["miss", "drop", "downgrade", "weak", "lawsuit", "fraud", "bear"]
            score = 0
            lower = text.lower()
            for word in pos_words:
                if word in lower:
                    score += 1
            for word in neg_words:
                if word in lower:
                    score -= 1
            if score > 0:
                return "positive", min(1.0, 0.55 + score * 0.08)
            if score < 0:
                return "negative", max(-1.0, -0.55 + score * 0.08)
            return "neutral", 0.0

        result = self.sentiment_pipe(text[:400])[0]
        label = result.get("label", "NEUTRAL").lower()
        confidence = float(result.get("score", 0.5))

        if "pos" in label:
            return "positive", round(confidence, 4)
        if "neg" in label:
            return "negative", round(-confidence, 4)
        return "neutral", 0.0

    def _normalize_text(self, value: str) -> str:
        value = re.sub(r"\s+", " ", (value or "").strip().lower())
        return value[:240]

    def _article_dedupe_key(self, ticker: str, headline: str, url: str, published_at: datetime) -> str:
        normalized_url = (url or "").strip().lower()
        if normalized_url:
            basis = f"{ticker.upper()}|url|{normalized_url}"
        else:
            published_bucket = published_at.replace(second=0, microsecond=0).isoformat()
            basis = f"{ticker.upper()}|headline|{self._normalize_text(headline)}|{published_bucket}"
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()

    def _parse_finnhub_news(self, ticker: str, items: list[dict]) -> list[dict]:
        parsed: list[dict] = []
        seen: set[str] = set()
        for item in items:
            unix_ts = int(item.get("datetime", 0) or 0)
            published_at = datetime.utcfromtimestamp(unix_ts) if unix_ts > 0 else datetime.utcnow()
            headline = str(item.get("headline") or "No headline").strip()
            summary = str(item.get("summary") or "").strip()
            source = str(item.get("source") or "Finnhub").strip() or "Finnhub"
            url = str(item.get("url") or "").strip()
            if not headline:
                continue
            dedupe_key = self._article_dedupe_key(ticker, headline, url, published_at)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            sentiment_label, sentiment_score = self.analyze_sentiment(f"{headline}. {summary}")
            parsed.append(
                {
                    "ticker": ticker,
                    "headline": headline[:512],
                    "summary": summary,
                    "source": source[:128],
                    "url": url[:1024],
                    "dedupe_key": dedupe_key,
                    "sentiment_label": sentiment_label,
                    "sentiment_score": sentiment_score,
                    "published_at": published_at,
                }
            )
        parsed.sort(key=lambda article: article["published_at"], reverse=True)
        return parsed

    async def fetch_news(self, ticker: str, limit: int = 20, max_age_days: int = 3) -> list[dict]:
        ticker = ticker.upper()
        from_date = (datetime.utcnow() - timedelta(days=max_age_days)).date().isoformat()
        to_date = datetime.utcnow().date().isoformat()

        if not settings.finnhub_api_key:
            if settings.live_data_only:
                raise RuntimeError("FINNHUB_API_KEY is required for live news mode.")
            return []

        started = datetime.utcnow()
        url = "https://finnhub.io/api/v1/company-news"
        try:
            resp = await self.client.get(
                url,
                params={"symbol": ticker, "from": from_date, "to": to_date, "token": settings.finnhub_api_key},
            )
            resp.raise_for_status()
            items = resp.json() or []
            parsed = self._parse_finnhub_news(ticker, items[: max(limit * 3, limit)])
            self._record_provider("finnhub_news", bool(parsed), latency_ms=(datetime.utcnow() - started).total_seconds() * 1000.0, error=None if parsed else "empty news")
            return parsed[:limit]
        except Exception as exc:
            self._record_provider("finnhub_news", False, latency_ms=(datetime.utcnow() - started).total_seconds() * 1000.0, error=str(exc))
            raise

    async def save_articles(self, db: AsyncSession, articles: list[dict], keep_recent: int = 60) -> list[NewsArticle]:
        if not articles:
            return []

        deduped: dict[str, dict] = {}
        for article in articles:
            ticker = str(article.get("ticker") or "").upper()
            headline = str(article.get("headline") or "").strip()
            url = str(article.get("url") or "").strip()
            published_at = article.get("published_at") or datetime.utcnow()
            if isinstance(published_at, datetime) and published_at.tzinfo is not None:
                published_at = published_at.astimezone(timezone.utc).replace(tzinfo=None)
            if not ticker or not headline:
                continue
            dedupe_key = str(article.get("dedupe_key") or self._article_dedupe_key(ticker, headline, url, published_at))
            candidate = {
                "ticker": ticker,
                "headline": headline[:512],
                "summary": str(article.get("summary") or ""),
                "source": str(article.get("source") or "Unknown")[:128],
                "url": url[:1024],
                "dedupe_key": dedupe_key,
                "sentiment_label": str(article.get("sentiment_label") or "neutral"),
                "sentiment_score": float(article.get("sentiment_score") or 0.0),
                "published_at": published_at,
            }
            existing = deduped.get(dedupe_key)
            if existing is None or candidate["published_at"] > existing["published_at"]:
                deduped[dedupe_key] = candidate

        payloads = list(deduped.values())
        if not payloads:
            return []

        tickers = sorted({article["ticker"] for article in payloads})
        keys = [article["dedupe_key"] for article in payloads]
        existing_stmt = select(NewsArticle).where(NewsArticle.ticker.in_(tickers), NewsArticle.dedupe_key.in_(keys))
        existing_rows = list((await db.execute(existing_stmt)).scalars().all())
        existing_by_key = {(row.ticker, row.dedupe_key): row for row in existing_rows}

        saved: list[NewsArticle] = []
        for payload in payloads:
            row = existing_by_key.get((payload["ticker"], payload["dedupe_key"]))
            if row is None:
                row = NewsArticle(**payload)
                db.add(row)
                saved.append(row)
                continue

            changed = False
            if payload["published_at"] >= row.published_at:
                for field in ("headline", "summary", "source", "url", "sentiment_label", "sentiment_score", "published_at"):
                    value = payload[field]
                    if getattr(row, field) != value:
                        setattr(row, field, value)
                        changed = True
            if changed:
                saved.append(row)

        await db.flush()

        for ticker in tickers:
            prune_stmt = (
                select(NewsArticle.id)
                .where(NewsArticle.ticker == ticker)
                .order_by(NewsArticle.published_at.desc(), NewsArticle.id.desc())
                .offset(max(keep_recent, 1))
            )
            stale_ids = [row_id for row_id in (await db.execute(prune_stmt)).scalars().all()]
            if stale_ids:
                await db.execute(delete(NewsArticle).where(NewsArticle.id.in_(stale_ids)))

        await db.commit()
        return saved

    async def get_latest_news(self, db: AsyncSession, ticker: str, limit: int = 20, max_age_hours: int = 96) -> list[NewsArticle]:
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        stmt = (
            select(NewsArticle)
            .where(
                NewsArticle.ticker == ticker.upper(),
                NewsArticle.published_at >= cutoff,
                or_(NewsArticle.url != "", NewsArticle.headline != ""),
            )
            .order_by(NewsArticle.published_at.desc(), NewsArticle.id.desc())
            .limit(limit * 3)
        )
        rows = list((await db.execute(stmt)).scalars().all())
        deduped: list[NewsArticle] = []
        seen: set[str] = set()
        for row in rows:
            dedupe_key = row.dedupe_key or self._article_dedupe_key(row.ticker, row.headline, row.url, row.published_at)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            deduped.append(row)
            if len(deduped) >= limit:
                break
        return deduped

    async def refresh_news(self, db: AsyncSession, ticker: str, limit: int = 20) -> list[NewsArticle]:
        articles = await self.fetch_news(ticker, limit=limit)
        await self.save_articles(db, articles)
        return await self.get_latest_news(db, ticker, limit=limit)
