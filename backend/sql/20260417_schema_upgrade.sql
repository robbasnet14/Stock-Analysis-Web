-- Manual SQL migration (optional) for environments without automatic startup DDL.

DROP TABLE IF EXISTS alert_conditions CASCADE;
DROP TABLE IF EXISTS alerts CASCADE;

CREATE TABLE IF NOT EXISTS holdings_lots (
  id BIGSERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  ticker VARCHAR(20) NOT NULL,
  asset_class VARCHAR(16) NOT NULL CHECK (asset_class IN ('equity','etf','crypto')),
  shares NUMERIC(20,8) NOT NULL,
  remaining_shares NUMERIC(20,8) NOT NULL,
  buy_price NUMERIC(20,8) NOT NULL,
  buy_ts TIMESTAMPTZ NOT NULL,
  status VARCHAR(8) NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_holdings_lots_user_ticker_status ON holdings_lots(user_id, ticker, status);

CREATE TABLE IF NOT EXISTS realized_trades (
  id BIGSERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  lot_id BIGINT REFERENCES holdings_lots(id) ON DELETE SET NULL,
  ticker VARCHAR(20) NOT NULL,
  sell_ts TIMESTAMPTZ NOT NULL,
  sell_price NUMERIC(20,8) NOT NULL,
  shares NUMERIC(20,8) NOT NULL,
  cost_basis NUMERIC(20,8) NOT NULL,
  pnl NUMERIC(20,8) NOT NULL
);

CREATE TABLE IF NOT EXISTS price_bars (
  ticker VARCHAR(20) NOT NULL,
  tf VARCHAR(8) NOT NULL,
  ts TIMESTAMPTZ NOT NULL,
  open NUMERIC(20,8),
  high NUMERIC(20,8),
  low NUMERIC(20,8),
  close NUMERIC(20,8),
  volume NUMERIC(20,0),
  source VARCHAR(16) NOT NULL,
  PRIMARY KEY (ticker, tf, ts)
);
CREATE INDEX IF NOT EXISTS idx_price_bars_ticker_tf_ts_desc ON price_bars(ticker, tf, ts DESC);

ALTER TABLE stock_prices ADD COLUMN IF NOT EXISTS interval VARCHAR(16) DEFAULT 'raw';
ALTER TABLE stock_prices ADD COLUMN IF NOT EXISTS source VARCHAR(32) DEFAULT 'unknown';
ALTER TABLE stock_prices ADD COLUMN IF NOT EXISTS is_live BOOLEAN DEFAULT FALSE;

ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS url_hash VARCHAR(40) DEFAULT '';
ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS title_hash VARCHAR(40) DEFAULT '';
ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS title TEXT DEFAULT '';
ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS sentiment VARCHAR(8) DEFAULT 'neutral';
ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS sentiment_model VARCHAR(24) DEFAULT '';
ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS ingested_at TIMESTAMP DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_news_articles_published_at_desc ON news_articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_articles_title_hash ON news_articles(title_hash);
CREATE UNIQUE INDEX IF NOT EXISTS uq_news_articles_url_hash_non_empty ON news_articles(url_hash) WHERE url_hash <> '';

CREATE TABLE IF NOT EXISTS news_article_tickers (
  article_id INTEGER REFERENCES news_articles(id) ON DELETE CASCADE,
  ticker VARCHAR(20) NOT NULL,
  PRIMARY KEY (article_id, ticker)
);
CREATE INDEX IF NOT EXISTS idx_news_article_tickers_ticker ON news_article_tickers(ticker);

CREATE TABLE IF NOT EXISTS signal_snapshots (
  id BIGSERIAL PRIMARY KEY,
  ticker VARCHAR(20) NOT NULL,
  horizon VARCHAR(8) NOT NULL,
  track VARCHAR(16) NOT NULL,
  action VARCHAR(12) NOT NULL,
  score NUMERIC(5,3) NOT NULL,
  confidence SMALLINT NOT NULL,
  payload JSONB NOT NULL,
  computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_signal_snapshots_ticker_horizon_track_computed_desc
  ON signal_snapshots(ticker, horizon, track, computed_at DESC);
