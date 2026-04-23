from datetime import datetime
from sqlalchemy import DateTime, Float, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class NewsArticle(Base):
    __tablename__ = "news_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # New normalized/dedup schema fields (backward-compatible with existing columns).
    url_hash: Mapped[str] = mapped_column(String(40), default="", index=True)
    title_hash: Mapped[str] = mapped_column(String(40), default="", index=True)
    title: Mapped[str] = mapped_column(Text, default="")
    ticker: Mapped[str] = mapped_column(String(12), index=True)
    headline: Mapped[str] = mapped_column(String(512))
    summary: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(128), default="Unknown")
    url: Mapped[str] = mapped_column(String(1024), default="")
    dedupe_key: Mapped[str] = mapped_column(String(256), default="", index=True)
    sentiment: Mapped[str] = mapped_column(String(8), default="neutral")
    sentiment_label: Mapped[str] = mapped_column(String(16), default="neutral")
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.0)
    sentiment_model: Mapped[str] = mapped_column(String(24), default="")
    published_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


Index("idx_news_ticker_published", NewsArticle.ticker, NewsArticle.published_at.desc())
Index("idx_news_ticker_dedupe", NewsArticle.ticker, NewsArticle.dedupe_key)
Index("idx_news_articles_published_at_desc", NewsArticle.published_at.desc())
Index("idx_news_articles_title_hash", NewsArticle.title_hash)
