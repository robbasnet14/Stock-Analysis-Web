# AI-Powered Stock Analytics Dashboard

Full-stack stock analytics platform with:

- Real-time stock streaming via WebSockets
- Live-provider-only market mode (no synthetic quote/news fallback when `LIVE_DATA_ONLY=true`)
- US symbol master ingestion from Finnhub (`/api/stocks/symbols/sync`) for full-market search
- Multi-provider candle failover (Finnhub -> Polygon -> TwelveData)
- News sentiment analysis (HuggingFace + fallback)
- Bull/Bear probability prediction (RandomForestClassifier)
- PostgreSQL persistence
- Redis cache + pub/sub stream layer
- React + TypeScript + Tailwind + Recharts dashboard
- Dockerized deployment with Docker Compose
- JWT auth + persistent user portfolios
- Registration with first/last name, DOB (18+), password confirmation and strength checks
- CSV holdings import (Robinhood-style exports) for one-shot portfolio setup
- Access/refresh token lifecycle with refresh-token revocation
- Broker integration-ready paper order simulation
- Broker account summary endpoint + UI panel
- User-scoped order status WebSocket stream (`/ws/orders`)
- Telegram-triggered price alerts
- Provider adapter layer for insider/options/dark-pool feeds
- Corporate actions engine (splits/dividends adjustments + user dividend credits)
- Provider/cache health endpoints (`/provider-status`, `/cache-status`, `/api/providers/status`, `/api/providers/cache-health`)
- Analytics-only mode (`ANALYTICS_ONLY_MODE=true`) to disable trading flows
- Market pulse endpoint (`/api/market/pulse`) for indices/gainers/losers/unusual volume
- Horizon-based bullish rankings (`short`, `mid`, `long`) and watchlist intelligence
- AI explanation endpoint (`/api/predictions/{ticker}/llm-explanation`) with OpenAI optional integration

## Architecture

```text
Market API
   -> FastAPI Data Worker
   -> PostgreSQL
   -> Redis cache/pubsub
   -> WebSocket stream
   -> React dashboard
```

## Tech Stack

### Frontend
- React
- TypeScript
- Vite
- TailwindCSS
- Recharts

### Backend
- Python
- FastAPI
- WebSockets
- pandas
- scikit-learn
- transformers (HuggingFace)

### Data & Infra
- PostgreSQL
- Redis
- Docker + Docker Compose

## Project Structure

```text
backend/
  app/
    main.py
    config.py
    api/
      stocks.py
      news.py
      predictions.py
    services/
      stock_service.py
      news_service.py
      ml_service.py
    models/
      stock.py
      news.py
      prediction.py
    websocket/
      manager.py
    db/
      database.py
    workers/
      data_collector.py

frontend/
  src/
    components/
      StockChart.tsx
      Watchlist.tsx
      NewsFeed.tsx
      PredictionCard.tsx
      PortfolioTracker.tsx
      PriceAlerts.tsx
      TrendingStocks.tsx
      StockSearch.tsx
    pages/
      Dashboard.tsx
    services/
      api.ts
      websocket.ts
    hooks/
      useStockStream.ts
```

## Setup (Docker - Recommended)

1. Copy env files:

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

2. Add your market API key in `backend/.env` (recommended):
- `FINNHUB_API_KEY=...`
 - Keep `LIVE_DATA_ONLY=true` for strict real market/news data only.
 - `python-multipart` is required for CSV upload endpoints (included in requirements).
 - Optional one-time symbol bootstrap on app start:
   - `SYMBOL_SYNC_ON_STARTUP=true`
3. Optional but recommended runtime config in `backend/.env`:
- `BROKER_MODE=paper` (or `alpaca`, `ibkr` when adapter credentials are wired)
- Alpaca live paper-trading mode:
  - `ALPACA_API_KEY=...`
  - `ALPACA_SECRET_KEY=...`
  - `ALPACA_BASE_URL=https://paper-api.alpaca.markets`
- `JWT_SECRET=...`
- `TELEGRAM_BOT_TOKEN=...`
- `SMTP_*` values for email alerts

4. Start all services:

```bash
docker compose up --build
```

5. Open apps:
- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`

## Setup (Local dev without Docker)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

## Core Features Implemented

1. Real-time stock data ingestion + WebSocket stream
2. Live dashboard with search, watchlist, chart, ticker, prediction, news
3. Data worker pipeline storing into Postgres and publishing to Redis + WS
4. Sentiment analysis on incoming news
5. RandomForest bull/bear prediction engine with technical indicators:
   - RSI
   - Moving averages
   - Volume change
   - Momentum
   - News sentiment adjustment
6. Authenticated users with persistent portfolio positions (PostgreSQL)
   - Roles: `admin`, `trader`, `viewer`
   - Refresh-token flow (`/auth/refresh`) and logout revocation
7. Paper order execution API designed for future broker adapter swap-in
8. Alert engine with Telegram push hooks
9. Provider adapters (`Polygon`/`UnusualWhales` compatible structure) for flow data
10. Notification fanout queue with retry worker (`telegram`, `email`, `webpush` channels)
11. Corporate actions processor (split-adjusted holdings + dividend credit ledger)
12. Provider and Redis health monitoring endpoints + UI panel

## Bonus Features Included

- Dark/light theme toggle
- Portfolio tracker widget
- Price alert widget
- Trending stocks panel
- AI-style prediction explanation endpoint

## Notes

- For real market data you should configure at least one provider key (`FINNHUB_API_KEY`, `POLYGON_API_KEY`, or `TWELVE_DATA_API_KEY`).
- If a primary candle source fails, backend automatically falls back to the next configured provider.
- This software is for educational/research use and not financial advice.
- Full endpoint reference is in [API_DOCUMENTATION.md](./API_DOCUMENTATION.md).
