import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from jose import JWTError
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from sqlalchemy import text
from app.api.auth import router as auth_router
from app.api.broker import router as broker_router
from app.api.watchlist import router as watchlist_router
from app.api.stocks import router as stocks_router
from app.api.market_data_alias import router as market_data_alias_router
from app.api.ensemble import router as ensemble_router
from app.api.market import router as market_router
from app.api.market_sectors import router as market_sectors_router
from app.api.trending import router as trending_router
from app.api.news import router as news_router
from app.api.portfolio import router as portfolio_router
from app.api.portfolio_optimizer import router as portfolio_optimizer_router
from app.api.predictions import router as predictions_router
from app.api.providers import router as providers_router
from app.api.strategy import router as strategy_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.signals import router as signals_router
from app.api.routes.signal_context import router as signal_context_router
from app.api.routes.account import router as account_router
from app.api.routes.search import router as search_router
from app.api.ws.prices import router as ws_prices_router
from app.api.ws.news import router as ws_news_router
from app.config import get_settings
from app.db.database import Base, engine
from app.db.database import SessionLocal
from app.models import StockPrice, NewsArticle, Prediction, User, UserProfile, SymbolMaster, PortfolioPosition, PaperOrder
from app.models import WatchlistItem, PortfolioSnapshot
from app.services.auth_service import decode_token
from app.state import state
from app.workers.data_collector import collect_forever
from app.workers.market_stream import stream_market_forever
from app.workers.notification_worker import dispatch_notifications_forever
from app.workers.order_sync_worker import sync_orders_forever
from app.workers.portfolio_snapshot_worker import snapshot_portfolios_forever
from app.workers.corporate_actions_worker import process_corporate_actions_forever
from app.workers.crypto_stream import stream_crypto_forever
from app.workers.news_poller import poll_news_forever
from app.workers.signal_warmer import warm_signals_forever


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Safe schema hardening for projects running without Alembic.
        await conn.execute(text("DROP TABLE IF EXISTS alert_conditions CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS alerts CASCADE"))
        # Backfill columns for older local DBs where stock_prices/news_articles were created before recent schema.
        await conn.execute(text("ALTER TABLE stock_prices ADD COLUMN IF NOT EXISTS interval VARCHAR(16) DEFAULT 'raw'"))
        await conn.execute(text("ALTER TABLE stock_prices ADD COLUMN IF NOT EXISTS source VARCHAR(32) DEFAULT 'unknown'"))
        await conn.execute(text("ALTER TABLE stock_prices ADD COLUMN IF NOT EXISTS is_live BOOLEAN DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS url_hash VARCHAR(40) DEFAULT ''"))
        await conn.execute(text("ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS title_hash VARCHAR(40) DEFAULT ''"))
        await conn.execute(text("ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS title TEXT DEFAULT ''"))
        await conn.execute(text("ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS dedupe_key VARCHAR(256) DEFAULT ''"))
        await conn.execute(text("ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS sentiment VARCHAR(8) DEFAULT 'neutral'"))
        await conn.execute(text("ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS sentiment_model VARCHAR(24) DEFAULT ''"))
        await conn.execute(text("ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS ingested_at TIMESTAMP DEFAULT now()"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_holdings_lots_user_ticker_status ON holdings_lots (user_id, ticker, status)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_holdings_lots_user_status ON holdings_lots (user_id, status)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_holdings_lots_user_ticker ON holdings_lots (user_id, ticker)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_price_bars_ticker_tf_ts_desc ON price_bars (ticker, tf, ts DESC)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_price_bars_ticker_tf_ts ON price_bars (ticker, tf, ts DESC)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_news_articles_published_at_desc ON news_articles (published_at DESC)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_news_published ON news_articles (published_at DESC)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_news_articles_title_hash ON news_articles (title_hash)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_news_article_tickers_ticker ON news_article_tickers (ticker)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_news_ticker ON news_article_tickers (ticker, article_id)"))
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_signal_snapshots_ticker_horizon_track_computed_desc "
                "ON signal_snapshots (ticker, horizon, track, computed_at DESC)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_signals_ticker_horizon_ts "
                "ON signal_snapshots (ticker, horizon, track, computed_at DESC)"
            )
        )
        await conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_news_articles_url_hash_non_empty "
                "ON news_articles (url_hash) WHERE url_hash <> ''"
            )
        )
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_watchlists_user_id ON watchlists (user_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_watchlists_symbol ON watchlists (symbol)"))

    state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    state.market_data.bind_redis(state.redis)
    state.notifications.bind_redis(state.redis)
    state.watchlist.update(settings.ticker_list)

    if settings.symbol_sync_on_startup and settings.finnhub_api_key:
        async with SessionLocal() as db:
            try:
                rows = await state.market_data.symbol_master()
                for item in rows:
                    symbol = str(item.get("symbol", "")).upper().strip()
                    if not symbol or len(symbol) > 24:
                        continue
                    description = str(item.get("description", "")).strip()
                    type_ = str(item.get("type", "")).strip()
                    display = str(item.get("displaySymbol", symbol)).strip()
                    currency = str(item.get("currency", "")).strip()
                    mic = str(item.get("mic", "")).strip()

                    row = await db.get(SymbolMaster, symbol)
                    if row is None:
                        db.add(
                            SymbolMaster(
                                symbol=symbol,
                                name=description,
                                exchange="US",
                                type=type_,
                                display_symbol=display,
                                currency=currency,
                                mic=mic,
                                updated_at=datetime.utcnow(),
                            )
                        )
                    else:
                        row.name = description
                        row.type = type_
                        row.display_symbol = display
                        row.currency = currency
                        row.mic = mic
                        row.updated_at = datetime.utcnow()
                await db.commit()
            except Exception:
                pass

    collector_task = asyncio.create_task(collect_forever())
    stream_task = None
    if settings.market_stream_enabled and (
        settings.finnhub_api_key
        or settings.polygon_api_key
        or (settings.alpaca_api_key and settings.alpaca_secret_key)
    ):
        stream_task = asyncio.create_task(stream_market_forever())
    notification_task = asyncio.create_task(dispatch_notifications_forever())
    snapshot_task = asyncio.create_task(snapshot_portfolios_forever())
    corporate_actions_task = asyncio.create_task(process_corporate_actions_forever())
    crypto_stream_task = asyncio.create_task(stream_crypto_forever())
    news_poller_task = asyncio.create_task(poll_news_forever())
    signal_warmer_task = asyncio.create_task(warm_signals_forever())
    state.tasks.append(collector_task)
    if stream_task is not None:
        state.tasks.append(stream_task)
    state.tasks.append(notification_task)
    if not settings.analytics_only_mode:
        order_sync_task = asyncio.create_task(sync_orders_forever())
        state.tasks.append(order_sync_task)
    state.tasks.append(snapshot_task)
    state.tasks.append(corporate_actions_task)
    state.tasks.append(crypto_stream_task)
    state.tasks.append(news_poller_task)
    state.tasks.append(signal_warmer_task)

    yield

    for task in state.tasks:
        task.cancel()

    if state.redis is not None:
        await state.redis.aclose()

    await state.stock_service.close()
    await state.market_data.close()
    await state.news_service.close()
    await state.llm_service.close()
    await state.sector_service.close()
    await state.notifications.close()
    await state.broker.close()


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:5173", "http://frontend:80"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> dict:
    return {"service": settings.app_name, "status": "ok"}


@app.get("/health")
async def health() -> dict:
    return {"status": "healthy"}


@app.get("/provider-status")
async def provider_status() -> dict:
    return {"providers": state.market_data.provider_health()}


@app.get("/cache-status")
async def cache_status() -> dict:
    if state.redis is None:
        return {"ok": False, "redis_connected": False, "error": "Redis client not initialized"}
    try:
        pong = await state.redis.ping()
        keys = await state.redis.dbsize()
        return {"ok": bool(pong), "redis_connected": bool(pong), "db_keys": int(keys or 0)}
    except Exception as exc:
        return {"ok": False, "redis_connected": False, "error": str(exc)}


app.include_router(stocks_router, prefix=settings.api_prefix)
app.include_router(market_data_alias_router, prefix=settings.api_prefix)
app.include_router(ensemble_router, prefix=settings.api_prefix)
app.include_router(market_router, prefix=settings.api_prefix)
app.include_router(market_sectors_router, prefix=settings.api_prefix)
app.include_router(trending_router, prefix=settings.api_prefix)
app.include_router(news_router, prefix=settings.api_prefix)
app.include_router(predictions_router, prefix=settings.api_prefix)
app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(watchlist_router, prefix=settings.api_prefix)
app.include_router(portfolio_router, prefix=settings.api_prefix)
app.include_router(portfolio_optimizer_router, prefix=settings.api_prefix)
app.include_router(providers_router, prefix=settings.api_prefix)
app.include_router(strategy_router, prefix=settings.api_prefix)
app.include_router(broker_router, prefix=settings.api_prefix)
app.include_router(dashboard_router, prefix=settings.api_prefix)
app.include_router(signals_router, prefix=settings.api_prefix)
app.include_router(signal_context_router, prefix=settings.api_prefix)
app.include_router(account_router, prefix=settings.api_prefix)
app.include_router(search_router, prefix=settings.api_prefix)
app.include_router(ws_prices_router)
app.include_router(ws_news_router)


@app.websocket("/ws/stocks/{ticker}")
async def stock_websocket(websocket: WebSocket, ticker: str):
    symbol = ticker.upper()
    await state.websocket.connect(symbol, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        state.websocket.disconnect(symbol, websocket)


@app.websocket("/ws/orders")
async def orders_websocket(websocket: WebSocket, token: str | None = None):
    if settings.analytics_only_mode:
        await websocket.close(code=1008)
        return
    if not token:
        await websocket.close(code=1008)
        return

    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise ValueError("invalid type")
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        await websocket.close(code=1008)
        return

    async with SessionLocal() as db:
        user = await db.get(User, user_id)
        if user is None:
            await websocket.close(code=1008)
            return

    await state.order_websocket.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        state.order_websocket.disconnect(user_id, websocket)


@app.websocket("/ws/watchlist")
async def watchlist_websocket(websocket: WebSocket, token: str | None = None):
    if not token:
        await websocket.close(code=1008)
        return

    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise ValueError("invalid type")
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        await websocket.close(code=1008)
        return

    async with SessionLocal() as db:
        user = await db.get(User, user_id)
        if user is None:
            await websocket.close(code=1008)
            return

    await state.watchlist_websocket.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        state.watchlist_websocket.disconnect(user_id, websocket)
