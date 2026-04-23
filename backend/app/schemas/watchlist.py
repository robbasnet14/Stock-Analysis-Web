from datetime import datetime
from pydantic import BaseModel, Field


class WatchlistAddIn(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=24)


class WatchlistMutationOut(BaseModel):
    status: str
    symbol: str | None = None


class WatchlistItemOut(BaseModel):
    symbol: str
    name: str
    price: float
    change: float
    percent: float
    created_at: datetime | None = None
