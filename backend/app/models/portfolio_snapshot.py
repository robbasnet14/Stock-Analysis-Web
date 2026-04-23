from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    value: Mapped[float] = mapped_column(Float, default=0.0)


Index("idx_portfolio_snapshots_user_ts", PortfolioSnapshot.user_id, PortfolioSnapshot.timestamp.desc())
