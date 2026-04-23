from datetime import datetime
from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class HoldingsLot(Base):
    __tablename__ = "holdings_lots"
    __table_args__ = (
        CheckConstraint("asset_class IN ('equity','etf','crypto')", name="ck_holdings_lots_asset_class"),
        CheckConstraint("status IN ('open','closed')", name="ck_holdings_lots_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    asset_class: Mapped[str] = mapped_column(String(16), default="equity")
    shares: Mapped[float] = mapped_column(Numeric(20, 8))
    remaining_shares: Mapped[float] = mapped_column(Numeric(20, 8))
    buy_price: Mapped[float] = mapped_column(Numeric(20, 8))
    buy_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String(8), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


Index("idx_holdings_lots_user_ticker_status", HoldingsLot.user_id, HoldingsLot.ticker, HoldingsLot.status)


class RealizedTrade(Base):
    __tablename__ = "realized_trades"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    lot_id: Mapped[int | None] = mapped_column(ForeignKey("holdings_lots.id", ondelete="SET NULL"), nullable=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    sell_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    sell_price: Mapped[float] = mapped_column(Numeric(20, 8))
    shares: Mapped[float] = mapped_column(Numeric(20, 8))
    cost_basis: Mapped[float] = mapped_column(Numeric(20, 8))
    pnl: Mapped[float] = mapped_column(Numeric(20, 8))


Index("idx_realized_trades_user_ticker_sell_ts", RealizedTrade.user_id, RealizedTrade.ticker, RealizedTrade.sell_ts.desc())
