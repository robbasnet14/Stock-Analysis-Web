from datetime import datetime
from sqlalchemy import DateTime, Float, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ticker: Mapped[str] = mapped_column(String(12), index=True)
    bull_probability: Mapped[float] = mapped_column(Float, default=0.5)
    bear_probability: Mapped[float] = mapped_column(Float, default=0.5)
    reasons: Mapped[str] = mapped_column(Text, default="[]")
    model_version: Mapped[str] = mapped_column(String(64), default="rf-v1")
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


Index("idx_predictions_ticker_time", Prediction.ticker, Prediction.generated_at.desc())
