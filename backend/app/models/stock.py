from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, Integer, String, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class StockPrice(Base):
    __tablename__ = "stock_prices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ticker: Mapped[str] = mapped_column(String(12), index=True)
    price: Mapped[float] = mapped_column(Float)
    change_percent: Mapped[float] = mapped_column(Float, default=0.0)
    volume: Mapped[int] = mapped_column(Integer, default=0)
    open_price: Mapped[float] = mapped_column(Float, default=0.0)
    high_price: Mapped[float] = mapped_column(Float, default=0.0)
    low_price: Mapped[float] = mapped_column(Float, default=0.0)
    interval: Mapped[str] = mapped_column(String(16), default="raw", index=True)
    source: Mapped[str] = mapped_column(String(32), default="unknown")
    is_live: Mapped[bool] = mapped_column(Boolean, default=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


Index("idx_stock_prices_ticker_ts", StockPrice.ticker, StockPrice.timestamp.desc())
Index("idx_stock_prices_ticker_interval_ts", StockPrice.ticker, StockPrice.interval, StockPrice.timestamp.desc())
