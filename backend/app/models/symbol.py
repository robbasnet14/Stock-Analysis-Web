from datetime import datetime
from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class SymbolMaster(Base):
    __tablename__ = "symbols"

    symbol: Mapped[str] = mapped_column(String(24), primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(512), default="")
    exchange: Mapped[str] = mapped_column(String(24), default="US", index=True)
    type: Mapped[str] = mapped_column(String(64), default="")
    display_symbol: Mapped[str] = mapped_column(String(24), default="")
    currency: Mapped[str] = mapped_column(String(16), default="")
    mic: Mapped[str] = mapped_column(String(16), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
