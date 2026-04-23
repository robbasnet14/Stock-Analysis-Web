from datetime import datetime
from sqlalchemy import DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class TechnicalIndicator(Base):
    __tablename__ = "technical_indicators"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ticker: Mapped[str] = mapped_column(String(24), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    rsi: Mapped[float] = mapped_column(Float, default=50.0)
    macd: Mapped[float] = mapped_column(Float, default=0.0)
    macd_signal: Mapped[float] = mapped_column(Float, default=0.0)
    adx: Mapped[float] = mapped_column(Float, default=0.0)
    bollinger_upper: Mapped[float] = mapped_column(Float, default=0.0)
    bollinger_lower: Mapped[float] = mapped_column(Float, default=0.0)
    sma20: Mapped[float] = mapped_column(Float, default=0.0)
    sma50: Mapped[float] = mapped_column(Float, default=0.0)
    sma200: Mapped[float] = mapped_column(Float, default=0.0)
    roc_5: Mapped[float] = mapped_column(Float, default=0.0)
    roc_20: Mapped[float] = mapped_column(Float, default=0.0)
    obv: Mapped[float] = mapped_column(Float, default=0.0)
    vwap: Mapped[float] = mapped_column(Float, default=0.0)
    volume_spike: Mapped[float] = mapped_column(Float, default=0.0)


Index("idx_technical_indicators_ticker_ts", TechnicalIndicator.ticker, TechnicalIndicator.timestamp.desc())
