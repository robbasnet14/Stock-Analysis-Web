from datetime import date, datetime
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class StockSplit(Base):
    __tablename__ = "stock_splits"
    __table_args__ = (
        UniqueConstraint("ticker", "effective_date", "from_factor", "to_factor", name="uq_split_unique"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ticker: Mapped[str] = mapped_column(String(24), index=True)
    effective_date: Mapped[date] = mapped_column(Date, index=True)
    from_factor: Mapped[float] = mapped_column(Float, default=1.0)
    to_factor: Mapped[float] = mapped_column(Float, default=1.0)
    applied: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DividendEvent(Base):
    __tablename__ = "dividend_events"
    __table_args__ = (
        UniqueConstraint("ticker", "pay_date", "cash_amount", name="uq_dividend_unique"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ticker: Mapped[str] = mapped_column(String(24), index=True)
    ex_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    pay_date: Mapped[date] = mapped_column(Date, index=True)
    cash_amount: Mapped[float] = mapped_column(Float, default=0.0)
    applied: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UserDividendCredit(Base):
    __tablename__ = "user_dividend_credits"
    __table_args__ = (
        UniqueConstraint("user_id", "ticker", "pay_date", name="uq_user_dividend"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    ticker: Mapped[str] = mapped_column(String(24), index=True)
    pay_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
