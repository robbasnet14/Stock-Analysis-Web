from datetime import datetime
from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, JSON, Numeric, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class SignalSnapshot(Base):
    __tablename__ = "signal_snapshots"
    __table_args__ = (
        CheckConstraint("horizon IN ('short','medium','long')", name="ck_signal_snapshots_horizon"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    horizon: Mapped[str] = mapped_column(String(8))
    track: Mapped[str] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(12))
    score: Mapped[float] = mapped_column(Numeric(5, 3))
    confidence: Mapped[int] = mapped_column(SmallInteger)
    payload: Mapped[dict] = mapped_column(JSON)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


Index(
    "idx_signal_snapshots_ticker_horizon_track_computed_desc",
    SignalSnapshot.ticker,
    SignalSnapshot.horizon,
    SignalSnapshot.track,
    SignalSnapshot.computed_at.desc(),
)
