from datetime import datetime
from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class SymbolFundamental(Base):
    __tablename__ = "symbol_fundamentals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    symbol: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    sector: Mapped[str] = mapped_column(String(128), default="")
    industry: Mapped[str] = mapped_column(String(256), default="")
    provider: Mapped[str] = mapped_column(String(64), default="finnhub")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


Index("idx_symbol_fundamentals_symbol_updated", SymbolFundamental.symbol, SymbolFundamental.updated_at.desc())
