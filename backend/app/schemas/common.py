from datetime import datetime
from pydantic import BaseModel


class StockTick(BaseModel):
    ticker: str
    price: float
    change_percent: float
    volume: int
    open_price: float
    high_price: float
    low_price: float
    timestamp: datetime
    source: str = ""


class NewsItem(BaseModel):
    ticker: str
    headline: str
    summary: str
    source: str
    url: str
    sentiment_label: str
    sentiment_score: float
    published_at: datetime


class PredictionOut(BaseModel):
    ticker: str
    bull_probability: float
    bear_probability: float
    reasons: list[str]
    generated_at: datetime


class WatchlistUpdate(BaseModel):
    ticker: str
