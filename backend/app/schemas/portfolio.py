from datetime import datetime
from pydantic import BaseModel


class PositionIn(BaseModel):
    ticker: str
    quantity: float
    avg_cost: float


class PositionOut(BaseModel):
    id: int
    ticker: str
    quantity: float
    avg_cost: float
    updated_at: datetime


class OrderIn(BaseModel):
    ticker: str
    side: str
    quantity: float
    order_type: str = "market"
    requested_price: float | None = None


class AlertIn(BaseModel):
    ticker: str
    direction: str = "above"
    target_price: float
