from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class NewsArticleTicker(Base):
    __tablename__ = "news_article_tickers"

    article_id: Mapped[int] = mapped_column(Integer, ForeignKey("news_articles.id", ondelete="CASCADE"), primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)


Index("idx_news_article_tickers_ticker", NewsArticleTicker.ticker)
