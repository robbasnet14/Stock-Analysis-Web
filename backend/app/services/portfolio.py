from __future__ import annotations

from dataclasses import dataclass
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd
from lttb import downsample
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.holdings_lot import HoldingsLot


logger = logging.getLogger(__name__)


RANGE_CONFIG = {
    "1D": {"lookback_days": 1, "tf": "1Min", "max_points": 390, "anchor": "intraday"},
    "1W": {"lookback_days": 7, "tf": "5Min", "max_points": 400, "anchor": "intraday"},
    "1M": {"lookback_days": 31, "tf": "15Min", "max_points": 500, "anchor": "intraday"},
    "3M": {"lookback_days": 93, "tf": "1Hour", "max_points": 500, "anchor": "intraday"},
    "1Y": {"lookback_days": 365, "tf": "1Day", "max_points": 260, "anchor": "daily"},
    "ALL": {"lookback_days": 3650, "tf": "1Day", "max_points": 500, "anchor": "daily"},
}


@dataclass
class PositionCalc:
    ticker: str
    quantity: float
    avg_cost: float
    live_price: float

    @property
    def market_value(self) -> float:
        return self.quantity * self.live_price

    @property
    def cost_basis(self) -> float:
        return self.quantity * self.avg_cost

    @property
    def pnl(self) -> float:
        return self.market_value - self.cost_basis


def summarize_positions(rows: list[PositionCalc]) -> dict:
    mv = sum(r.market_value for r in rows)
    cb = sum(r.cost_basis for r in rows)
    pnl = mv - cb
    pct = (pnl / cb * 100.0) if cb > 0 else 0.0
    return {"market_value": mv, "cost_basis": cb, "pnl": pnl, "pnl_percent": pct}


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _bar_close(bar: dict[str, Any]) -> float:
    return float(bar.get("close") or bar.get("price") or 0.0)


def _bar_timestamp(bar: dict[str, Any]) -> pd.Timestamp | None:
    ts = pd.to_datetime(bar.get("timestamp"), utc=True, errors="coerce")
    if pd.isna(ts):
        return None
    return ts


def _is_us_market_open(dt: datetime) -> bool:
    utc = _as_utc(dt) or datetime.now(timezone.utc)
    minutes = utc.hour * 60 + utc.minute
    # Broad UTC window that covers regular US market hours across DST.
    return utc.weekday() < 5 and (13 * 60 + 30) <= minutes <= (21 * 60)


async def _latest_live_price(redis_client, ticker: str, fallback: float) -> float:
    symbol = ticker.upper()
    if redis_client is None:
        return fallback

    try:
        hash_price = await redis_client.hget("price:latest", symbol)
        if hash_price is not None:
            price = float(hash_price)
            if price > 0:
                return price
    except Exception:
        pass

    for key in (f"price:{symbol}", f"latest:{symbol}"):
        try:
            raw = await redis_client.get(key)
        except Exception:
            raw = None
        if not raw:
            continue
        try:
            if key.startswith("latest:"):
                import json

                price = float(json.loads(raw).get("price") or 0.0)
            else:
                price = float(raw)
            if price > 0:
                return price
        except Exception:
            continue

    return fallback


async def compute_portfolio_timeseries(
    *,
    db: AsyncSession,
    market_data,
    redis_client,
    user_id: int,
    range_key: str,
) -> list[dict[str, float]]:
    key = (range_key or "1D").upper()
    config = RANGE_CONFIG[key]

    stmt = (
        select(HoldingsLot)
        .where(HoldingsLot.user_id == user_id, HoldingsLot.status == "open")
        .order_by(HoldingsLot.buy_ts.asc(), HoldingsLot.id.asc())
    )
    lots = list((await db.execute(stmt)).scalars().all())
    lots = [lot for lot in lots if float(lot.remaining_shares or lot.shares or 0.0) > 0 and str(lot.ticker or "").strip()]
    if not lots:
        return []

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=int(config["lookback_days"]))
    earliest_buy = min(_as_utc(lot.buy_ts if isinstance(lot.buy_ts, datetime) else None) or now for lot in lots)
    if earliest_buy > start:
        start = earliest_buy

    unique_tickers = sorted({str(lot.ticker).upper().strip() for lot in lots})
    bars_by_ticker: dict[str, pd.Series] = {}

    for ticker in unique_tickers:
        ticker_lots = [lot for lot in lots if str(lot.ticker).upper().strip() == ticker]
        first_lot = min(ticker_lots, key=lambda lot: _as_utc(lot.buy_ts if isinstance(lot.buy_ts, datetime) else None) or now)
        first_buy_ts = _as_utc(first_lot.buy_ts if isinstance(first_lot.buy_ts, datetime) else None) or start
        first_buy_price = float(first_lot.buy_price or 0.0)
        try:
            payload = await market_data.get_bars(ticker, key, tf=str(config["tf"]))
            bars = payload.get("bars") or []
        except Exception:
            logger.warning("No bars for %s in range %s", ticker, key)
            bars = []

        points: dict[pd.Timestamp, float] = {}
        for bar in bars:
            ts = _bar_timestamp(bar)
            close = _bar_close(bar)
            if ts is None or close <= 0:
                continue
            if ts.to_pydatetime() < start or ts.to_pydatetime() > now:
                continue
            points[ts] = close

        for lot in ticker_lots:
            buy_ts = _as_utc(lot.buy_ts if isinstance(lot.buy_ts, datetime) else None) or start
            buy_price = float(lot.buy_price or 0.0)
            if start <= buy_ts <= now and buy_price > 0:
                points[pd.Timestamp(buy_ts)] = buy_price

        if not points and first_buy_price > 0:
            points[pd.Timestamp(start)] = first_buy_price

        if not points:
            logger.warning("No bars for %s in range %s", ticker, key)
            continue

        series = pd.Series(points, name=ticker, dtype=float).sort_index()
        series = series[~series.index.duplicated(keep="last")]
        bars_by_ticker[ticker] = series

    if not bars_by_ticker:
        return []

    all_timestamps = sorted(set().union(*[set(s.index) for s in bars_by_ticker.values()]))
    timestamp_index = pd.DatetimeIndex(all_timestamps)
    if timestamp_index.empty:
        return []

    price_df = pd.DataFrame(index=timestamp_index)
    for ticker, series in bars_by_ticker.items():
        price_df[ticker] = series.reindex(timestamp_index).ffill()
        first_lot_for_ticker = min(
            (lot for lot in lots if str(lot.ticker).upper().strip() == ticker),
            key=lambda lot: _as_utc(lot.buy_ts if isinstance(lot.buy_ts, datetime) else None) or now,
        )
        price_df[ticker] = price_df[ticker].fillna(float(first_lot_for_ticker.buy_price or 0.0))

    shares_df = pd.DataFrame(0.0, index=timestamp_index, columns=unique_tickers)
    for lot in lots:
        ticker = str(lot.ticker).upper().strip()
        buy_ts = _as_utc(lot.buy_ts if isinstance(lot.buy_ts, datetime) else None) or start
        shares = float(lot.remaining_shares or lot.shares or 0.0)
        if ticker not in shares_df.columns or shares <= 0:
            continue
        shares_df.loc[timestamp_index >= pd.Timestamp(buy_ts), ticker] += shares

    value_series = (shares_df * price_df).sum(axis=1)

    if config["anchor"] == "intraday":
        last_hist_ts = value_series.index[-1]
        now_ts = pd.Timestamp(now)
        gap_minutes = max(0.0, (now_ts - last_hist_ts).total_seconds() / 60.0)
        live_total = 0.0
        for ticker in unique_tickers:
            if ticker not in shares_df.columns or ticker not in price_df.columns:
                continue
            shares_now = float(shares_df[ticker].iloc[-1])
            if shares_now <= 0:
                continue
            fallback = float(price_df[ticker].iloc[-1])
            live_price = await _latest_live_price(redis_client, ticker, fallback)
            live_total += shares_now * live_price
        if live_total > 0:
            if gap_minutes < 5:
                value_series.loc[now_ts] = live_total
            elif gap_minutes < 60:
                n_bridge = max(2, int(gap_minutes / 5))
                bridge_index = pd.date_range(start=last_hist_ts, end=now_ts, periods=n_bridge + 1)[1:]
                last_value = float(value_series.iloc[-1])
                bridge_values = np.linspace(last_value, live_total, n_bridge + 1)[1:]
                for ts, val in zip(bridge_index, bridge_values, strict=False):
                    value_series.loc[ts] = float(val)
            else:
                value_series.loc[now_ts] = live_total

        if _is_us_market_open(now) and gap_minutes > 60:
            logger.warning(
                "Stale historical bars during market hours: last_hist_ts=%s, gap_minutes=%.1f",
                last_hist_ts,
                gap_minutes,
            )

    value_series = value_series.sort_index()

    if value_series.isna().any():
        logger.warning("NaN values in timeseries for user %s, range %s", user_id, key)
        value_series = value_series.dropna()

    value_series = value_series[value_series > 0]
    if value_series.empty or bool((value_series == 0).all()):
        logger.warning("All-zero timeseries for user %s", user_id)
        return []

    diffs = value_series.diff().abs()
    flat_pct = float((diffs == 0).sum() / max(1, len(diffs)))
    if flat_pct > 0.5:
        logger.error(
            "FLAT TIMESERIES DETECTED for user %s, range %s: %.1f%% of points are identical to the previous point. "
            "This usually means shares or prices are not varying with time.",
            user_id,
            key,
            flat_pct * 100.0,
        )

    points = [
        {"time": int(ts.timestamp()), "value": float(val)}
        for ts, val in value_series.sort_index().items()
        if pd.notna(ts) and np.isfinite(val)
    ]

    if len(points) > int(config["max_points"]):
        arr = np.array([[p["time"], p["value"]] for p in points], dtype=float)
        ds = downsample(arr, n_out=int(config["max_points"]))
        points = [{"time": int(t), "value": float(v)} for t, v in ds]

    logger.info(
        "timeseries: user=%s range=%s lots=%s tickers=%s bars=%s points=%s flat_pct=%.1f%%",
        user_id,
        key,
        len(lots),
        len(unique_tickers),
        sum(len(s) for s in bars_by_ticker.values()),
        len(points),
        flat_pct * 100.0,
    )
    return points
