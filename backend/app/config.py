from functools import lru_cache
from urllib.parse import urlparse
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", protected_namespaces=("settings_",))

    app_name: str = "AI Stock Analytics Dashboard"
    env: str = "development"
    api_prefix: str = "/api"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/stockdb"
    redis_url: str = "redis://localhost:6379/0"
    vercel_url: str = ""
    log_level: str = "DEBUG"

    finnhub_api_key: str = ""
    alpha_vantage_api_key: str = ""
    polygon_api_key: str = ""
    tiingo_api_key: str = ""
    live_data_only: bool = True
    # Alpaca: keep legacy names for backward compatibility, prefer *_id/*_secret.
    alpaca_api_key_id: str = ""
    alpaca_api_secret_key: str = ""
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_data_feed: str = "iex"
    alpaca_data_base: str = "https://data.alpaca.markets"
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    alpaca_data_url: str = "https://data.alpaca.markets"
    alpaca_stream_url: str = "wss://stream.data.alpaca.markets/v2/iex"

    binance_ws_url: str = "wss://stream.binance.com:9443/stream"
    binance_rest_url: str = "https://api.binance.com"
    binance_us_fallback: bool = True

    coingecko_demo_key: str = ""
    coingecko_base: str = "https://api.coingecko.com/api/v3"

    marketaux_api_key: str = ""
    alphavantage_news_enabled: bool = True
    news_rss_sources: str = "yahoo,google_news"
    news_poll_interval_seconds: int = 60

    sentiment_primary: str = "gpt-4o-mini"
    sentiment_fallback: str = "vader"
    openai_sentiment_batch_size: int = 10

    provider_health_window_seconds: int = 300
    provider_failover_enabled: bool = True
    rate_limit_redis_prefix: str = "ratelimit:"

    feature_alerts_enabled: bool = False
    feature_candlestick_chart: bool = False

    broker_mode: str = "paper"
    analytics_only_mode: bool = True

    jwt_secret: str = "change-me-in-prod"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24

    telegram_bot_token: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    notification_retry_max: int = 3

    default_tickers: str = "AAPL,MSFT,TSLA,NVDA,AMZN"
    market_stream_enabled: bool = True
    market_stream_provider: str = "auto"
    market_stream_throttle_seconds: float = 1.0
    symbol_sync_on_startup: bool = False
    update_interval_seconds: int = 15
    model_retrain_minutes: int = 30
    frontend_origin: str = "http://localhost:5173"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    @model_validator(mode="after")
    def _coerce_legacy_provider_vars(self) -> "Settings":
        if self.database_url.startswith("postgres://"):
            self.database_url = self.database_url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif self.database_url.startswith("postgresql://") and "+asyncpg" not in self.database_url:
            self.database_url = self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        if not self.alpaca_api_key and self.alpaca_api_key_id:
            self.alpaca_api_key = self.alpaca_api_key_id
        if not self.alpaca_secret_key and self.alpaca_api_secret_key:
            self.alpaca_secret_key = self.alpaca_api_secret_key
        if not self.alpaca_data_url and self.alpaca_data_base:
            self.alpaca_data_url = self.alpaca_data_base
        if not self.alpaca_data_base and self.alpaca_data_url:
            self.alpaca_data_base = self.alpaca_data_url
        if self.env.lower() == "production" and self.log_level == "DEBUG":
            self.log_level = "INFO"
        return self

    @property
    def ticker_list(self) -> list[str]:
        return [t.strip().upper() for t in self.default_tickers.split(",") if t.strip()]

    @property
    def cors_origins(self) -> list[str]:
        origins = {self.frontend_origin, "http://localhost:5173", "http://frontend:80"}
        if self.vercel_url:
            raw = self.vercel_url.strip()
            parsed = urlparse(raw if "://" in raw else f"https://{raw}")
            if parsed.netloc:
                origins.add(f"https://{parsed.netloc}")
        return sorted(origin for origin in origins if origin)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
