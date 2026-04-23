from datetime import datetime
from sqlalchemy import DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    symbol: Mapped[str] = mapped_column(String(24), index=True)
    strategy: Mapped[str] = mapped_column(String(64), index=True)
    lookback_days: Mapped[int] = mapped_column(Integer, default=504)
    trades: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    avg_return: Mapped[float] = mapped_column(Float, default=0.0)
    max_drawdown: Mapped[float] = mapped_column(Float, default=0.0)
    cumulative_return: Mapped[float] = mapped_column(Float, default=0.0)
    meta_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


Index("idx_backtest_runs_symbol_created", BacktestRun.symbol, BacktestRun.created_at.desc())
