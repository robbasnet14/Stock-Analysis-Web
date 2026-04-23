# API Documentation

Base URL: `http://localhost:8000`

## Health

- `GET /health`
  - Response: `{ "status": "healthy" }`
- `GET /provider-status`
  - Provider success/failure counters and last latency/error snapshot.
- `GET /cache-status`
  - Redis connectivity and key-count snapshot.

## Stocks

- `GET /api/stocks/live-status`
- `GET /api/stocks/session`
  - Response:
    ```json
    {
      "session": "market",
      "is_open": true,
      "timestamp": "2026-04-04T14:22:01Z"
    }
    ```
- `GET /api/stocks/symbols/status`
- `POST /api/stocks/symbols/sync`
- `GET /api/stocks/search?q=TSLA`
- `POST /api/stocks/watchlist/add`
  - Body: `{ "ticker": "TSLA" }`
- `POST /api/stocks/watchlist/remove`
  - Body: `{ "ticker": "TSLA" }`
- `GET /api/stocks/{ticker}/latest`
- `GET /api/stocks/{ticker}/history?limit=180`
- `GET /api/stocks/{ticker}/candles?range=1D|1W|1M|1Y`
  - Live candles with provider failover chain: Finnhub -> Polygon -> TwelveData.
- `GET /api/stocks/trending/list`
- `GET /api/stocks/bull-cases/list?horizon=short|mid|long`
- `GET /api/stocks/bullish?horizon=short|mid|long`
- `GET /api/stocks/alpha-ranking?horizon=short|mid|long`
  - Multi-factor alpha ranking with factor transparency and risk metadata.
- `GET /api/stocks/ensemble-ranking?horizon=short|mid|long`
  - Ensemble ranking across factor/technical/sentiment/macro models.
- `GET /api/stocks/ensemble-diagnostics?horizon=short|mid|long`
  - Ensemble diagnostics with per-model feature contribution and confidence bands.
- `GET /api/stocks/market-regime`
  - Current market regime classification (`bull`, `bear`, `sideways`).
- `GET /api/stocks/{ticker}/technical`
  - Latest technical indicator snapshot (`RSI`, `MACD`, `ADX`, Bollinger, `SMA20/50/200`, `OBV`, `VWAP`, etc.).

## Watchlist (Bearer token required)

- `GET /api/watchlist`
  - Returns:
    ```json
    [
      {
        "symbol": "AAPL",
        "name": "Apple Inc",
        "price": 193.22,
        "change": -0.52,
        "percent": -0.27
      }
    ]
    ```
  - Price source priority: Redis `price:{symbol}` -> Redis `latest:{symbol}` -> Postgres latest `stock_prices` row.
- `POST /api/watchlist/add`
  - Body: `{ "symbol": "TSLA" }`
- `DELETE /api/watchlist/remove/{symbol}`
- `GET /api/watchlist/intelligence`
  - Returns sentiment, momentum, analyst-style rating, risk level, and volume ratio for watchlist symbols.
- `GET /api/stocks/bull-cases/list`
  - Returns live bull-case candidates ranked by current up-move, short-term momentum, and live volume ratio.

## Auth

- `POST /api/auth/register`
  - Body:
    ```json
    {
      "first_name": "Jane",
      "last_name": "Doe",
      "date_of_birth": "1998-06-21",
      "email": "you@example.com",
      "password": "Strong!Pass1",
      "password_confirm": "Strong!Pass1"
    }
    ```
  - Enforces age 18+ and strong password policy.
- `POST /api/auth/login`
  - Returns `{ "access_token", "refresh_token", "token_type" }`
- `POST /api/auth/refresh`
  - Body: `{ "refresh_token": "..." }`
- `POST /api/auth/logout`
  - Body: `{ "refresh_token": "..." }`
- `GET /api/auth/me` (Bearer token required)
  - Includes `first_name` and `last_name`
- `POST /api/auth/telegram?chat_id=<id>` (Bearer token required)

## Portfolio (Bearer token required)

- `GET /api/portfolio/positions`
- `GET /api/portfolio/value-history?range=1D|1W|1M|1Y`
  - Returns aggregated live portfolio value candles based on saved holdings.
- `GET /api/portfolio/history?range=1D|1W|1M|1Y`
  - Returns minute-level snapshot table values for Robinhood-style portfolio chart.
- `GET /api/portfolio/corporate-actions/recent`
  - Returns recent splits/dividends plus user dividend credits from applied actions.
- `POST /api/portfolio/import-csv` (multipart form-data, field name: `file`)
  - Imports holdings from CSV and upserts positions by ticker.
- `POST /api/portfolio/positions`
  - Body: `{ "ticker": "TSLA", "quantity": 5, "avg_cost": 210 }`
- `DELETE /api/portfolio/positions/{position_id}`
- `POST /api/portfolio/orders`
  - Body: `{ "ticker":"TSLA","side":"buy","quantity":1 }`
  - Uses pluggable broker mode (`paper`, `alpaca`, `ibkr`)
- `GET /api/portfolio/orders`
- `GET /api/portfolio/orders/{order_id}/status`
- `POST /api/portfolio/orders/{order_id}/cancel`
- `POST /api/portfolio/sync/positions`
  - Note: when `ANALYTICS_ONLY_MODE=true`, trading/broker-sync routes return `410`.
- `POST /api/portfolio/optimize`
  - Input:
    ```json
    { "symbols": ["AAPL", "NVDA", "MSFT", "AMZN"] }
    ```
  - Output includes optimized weights, expected return, volatility, and Sharpe ratio.

## Market

- `GET /api/market/pulse`
  - Returns:
    - index snapshot (`SPY`, `QQQ`, `DIA`)
    - top gainers/losers
    - unusual volume list
- `GET /api/market/sectors`
  - Sector rotation strength ranking with `avg_return_5d`, `avg_return_20d`, and `volume_strength`.
- `GET /api/market/trending`
  - Top trending stocks using multi-factor ranking (volume spike, 1D momentum, news frequency, sentiment).

## Broker (Bearer token required)

- `GET /api/broker/account`
  - Returns account summary from active broker adapter (`paper` or `alpaca`).

## Alerts (Bearer token required)

- `GET /api/alerts`
- `POST /api/alerts`
  - Body: `{ "ticker":"TSLA","direction":"above","target_price":230 }`
- `DELETE /api/alerts/{alert_id}`
- `POST /api/alerts/telegram/test`
  - Notification fanout channels are queued via Redis with retry logic (`telegram`, `email`, `webpush`).

## Provider Adapters

- `GET /api/providers/flow/{ticker}`
  - Returns dark-pool/options/insider snapshot using Polygon/UnusualWhales-compatible adapter structure.
- `GET /api/providers/status`
  - Returns provider health metrics (`configured`, `last_ok`, `last_error`, `last_latency_ms`, `successes`, `failures`).
- `GET /api/providers/cache-health`
  - Returns Redis cache health (`redis_connected`, `latency_ms`, `db_keys`).

## Admin (Admin role required)

- `GET /api/admin/users`
- `POST /api/admin/users/{user_id}/role?role=trader`

## News

- `GET /api/news/{ticker}`
  - Returns article list + average sentiment

## Predictions

- `GET /api/predictions/{ticker}`
  - Example:
    ```json
    {
      "ticker": "AAPL",
      "bull_probability": 0.72,
      "bear_probability": 0.28,
      "reasons": [
        "positive news sentiment",
        "RSI bounce setup",
        "volume spike"
      ],
      "generated_at": "2026-04-06T20:12:00.000000"
    }
    ```
- `GET /api/predictions/{ticker}/explanation`
- `GET /api/predictions/{ticker}/llm-explanation?horizon=short|mid|long`
  - Returns AI narrative from computed factors (uses OpenAI when configured, deterministic fallback otherwise).

## Strategy

- `POST /api/strategy/backtest`
  - Input:
    ```json
    { "symbol": "AAPL", "strategy": "rsi_oversold", "lookback_days": 504 }
    ```
  - Returns historical strategy metrics (`win_rate`, `avg_return`, `max_drawdown`, `cumulative_return`).
- `GET /api/strategy/backtest/history?symbol=AAPL&strategy=rsi_oversold&limit=50`
  - Returns persisted backtest run history ordered by most recent run.
- `GET /api/strategy/backtest/history/{run_id}`
  - Returns one persisted run with metadata payload.

## WebSocket

- `WS /ws/stocks/{ticker}`
  - Example: `ws://localhost:8000/ws/stocks/TSLA`
  - Stream payload example:
    ```json
    {
      "type": "tick",
      "ticker": "TSLA",
      "price": 213.21,
      "change_percent": 2.1,
      "volume": 11232111,
      "high_price": 215.1,
      "low_price": 209.8,
      "timestamp": "2026-04-06T20:12:00.000000",
      "prediction": {
        "ticker": "TSLA",
        "bull_probability": 0.72,
        "bear_probability": 0.28,
        "reasons": ["positive news sentiment", "volume spike"],
        "generated_at": "2026-04-06T20:12:00.000000"
      }
    }
    ```
- `WS /ws/orders?token=<access_token>`
  - User-scoped order updates for status changes (submitted/filled/canceled/partial fills).
  - Stream payload example:
    ```json
    {
      "type": "order_update",
      "order": {
        "id": 91,
        "ticker": "TSLA",
        "side": "buy",
        "quantity": 1,
        "order_type": "market",
        "requested_price": 0,
        "filled_price": 211.41,
        "status": "filled",
        "broker_mode": "alpaca",
        "broker_order_id": "7d3f...",
        "created_at": "2026-04-06T20:12:00.000000"
      }
    }
    ```
- `WS /ws/watchlist?token=<access_token>`
  - User-scoped price updates for watchlist symbols.
  - Stream payload example:
    ```json
    {
      "type": "price_update",
      "symbol": "AAPL",
      "price": 193.21,
      "timestamp": 1712238293
    }
    ```

## Interactive docs

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
