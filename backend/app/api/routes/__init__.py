from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.portfolio import router as portfolio_router
from app.api.routes.news import router as news_router
from app.api.routes.signals import router as signals_router
from app.api.routes.account import router as account_router
from app.api.routes.search import router as search_router

__all__ = [
    "dashboard_router",
    "portfolio_router",
    "news_router",
    "signals_router",
    "account_router",
    "search_router",
]
