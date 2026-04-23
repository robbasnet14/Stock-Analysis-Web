from typing import Any
from redis.asyncio import Redis
from app.websocket.manager import WebSocketManager
from app.websocket.order_manager import OrderWebSocketManager
from app.websocket.watchlist_manager import WatchlistWebSocketManager
from app.services.broker_service import BrokerService
from app.services.stock_service import StockService
from app.services.market_data import MarketDataService
from app.services.news_service import NewsService
from app.services.ml_service import MLService
from app.services.llm_service import LLMService
from app.services.ensemble_service import EnsembleService
from app.services.sector_service import SectorService
from app.services.portfolio_optimizer import PortfolioOptimizerService
from app.services.trending_service import TrendingService
from app.services.notification_service import NotificationService
from app.services.provider_service import ProviderAggregator


class AppState:
    def __init__(self) -> None:
        self.redis: Redis | None = None
        self.websocket = WebSocketManager()
        self.order_websocket = OrderWebSocketManager()
        self.watchlist_websocket = WatchlistWebSocketManager()
        self.stock_service = StockService()
        self.market_data = MarketDataService()
        self.news_service = NewsService()
        self.ml_service = MLService()
        self.llm_service = LLMService()
        self.ensemble_service = EnsembleService(self.stock_service)
        self.sector_service = SectorService(self.stock_service)
        self.portfolio_optimizer = PortfolioOptimizerService(self.stock_service)
        self.trending_service = TrendingService(self.stock_service)
        self.provider_aggregator = ProviderAggregator()
        self.notifications = NotificationService()
        self.broker = BrokerService()
        self.watchlist: set[str] = set()
        self.tasks: list[Any] = []


state = AppState()
