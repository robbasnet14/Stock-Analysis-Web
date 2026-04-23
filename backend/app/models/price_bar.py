from datetime import datetime
from sqlalchemy import DateTime, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class PriceBar(Base):
    __tablename__ = "price_bars"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    tf: Mapped[str] = mapped_column(String(8), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    open: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    high: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    low: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    close: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    volume: Mapped[float | None] = mapped_column(Numeric(20, 0), nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="unknown")


Index("idx_price_bars_ticker_tf_ts_desc", PriceBar.ticker, PriceBar.tf, PriceBar.ts.desc())
Index("idx_price_bars_ticker_tf_ts", PriceBar.ticker, PriceBar.tf, PriceBar.ts.desc())
