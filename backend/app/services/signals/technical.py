from __future__ import annotations

import json
import random
import asyncio
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.signals.horizons import params_for

try:
    import talib  # type: ignore
except Exception:  # pragma: no cover
    talib = None

from app.utils.ta import compute_adx, compute_bollinger, compute_macd, compute_rsi, ema

logger = logging.getLogger(__name__)


@dataclass
class IndicatorVote:
    name: str
    value: float
    vote: int
    weight: float
    fired_rule: str
    explanation: str


INDICATOR_WEIGHTS: dict[str, float] = {
    "rsi_crossback": 0.18,
    "macd_cross": 0.18,
    "ema_cross": 0.16,
    "bollinger_reclaim": 0.14,
    "stoch_oversold_cross": 0.14,
    "volume_confirmed_up": 0.12,
    "adx_gate": 0.08,
}

TREND_SIGNALS = {"macd_cross", "ema_cross", "volume_confirmed_up"}

HORIZON_MARKET_FETCH: dict[str, dict[str, Any]] = {
    "short": {"span": "1W", "tf": "5Min", "lookback_days": 3},
    "mid": {"span": "3M", "tf": "1Day", "lookback_days": 90},
    "long": {"span": "1Y", "tf": "1Day", "lookback_days": 365},
}


def _cache_ttl(horizon: str) -> int:
    cfg = params_for(horizon)
    base = int(cfg.get("cache_ttl", 60))
    return base + random.randint(0, 30)


def _series_from_rows(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    df = pd.DataFrame(rows)
    if "close" not in df.columns and "price" in df.columns:
        df["close"] = pd.to_numeric(df["price"], errors="coerce")
    for c_in, c_out in [("open_price", "open"), ("high_price", "high"), ("low_price", "low")]:
        if c_out not in df.columns and c_in in df.columns:
            df[c_out] = pd.to_numeric(df[c_in], errors="coerce")
    if "volume" not in df.columns:
        df["volume"] = 0.0
    if "timestamp" not in df.columns:
        df["timestamp"] = datetime.utcnow().isoformat()

    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce").ffill().bfill().fillna(0.0)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
    return df


def _trim_lookback(df: pd.DataFrame, lookback_days: int) -> pd.DataFrame:
    if df.empty:
        return df
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=int(lookback_days))
    trimmed = df[df["timestamp"] >= cutoff]
    return trimmed if not trimmed.empty else df


def _minimum_bars(horizon: str) -> int:
    cfg = params_for(horizon)
    slow_ema = int(cfg.get("ema_slow", 26))
    macd_slow = int(cfg.get("macd_slow", 26))
    adx_period = int(cfg.get("adx_period", 14))
    return max(slow_ema, macd_slow, adx_period * 2)


def _talib_or_fallback(df: pd.DataFrame, horizon: str) -> dict[str, np.ndarray]:
    close = df["close"].astype(float).to_numpy()
    high = df["high"].astype(float).to_numpy()
    low = df["low"].astype(float).to_numpy()
    volume = df["volume"].astype(float).to_numpy()
    cfg = params_for(horizon)
    rsi_period = int(cfg.get("rsi_period", 14))
    stoch_period = int(cfg.get("stoch_period", 14))
    ema_fast_n = int(cfg.get("ema_fast", 12))
    ema_slow_n = int(cfg.get("ema_slow", 26))

    if talib is not None:
        rsi = talib.RSI(close, timeperiod=rsi_period)
        macd, macd_signal, _ = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
        bb_up, _, bb_low = talib.BBANDS(close, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        stoch_k, stoch_d = talib.STOCH(high, low, close, fastk_period=stoch_period)
        adx = talib.ADX(high, low, close, timeperiod=14)
        ema_fast = talib.EMA(close, timeperiod=ema_fast_n)
        ema_slow = talib.EMA(close, timeperiod=ema_slow_n)
    else:
        s_close = pd.Series(close)
        s_high = pd.Series(high)
        s_low = pd.Series(low)
        s_vol = pd.Series(volume)
        rsi = compute_rsi(s_close, period=rsi_period).to_numpy()
        macd_s, macd_sig_s = compute_macd(s_close)
        macd = macd_s.to_numpy()
        macd_signal = macd_sig_s.to_numpy()
        bb_up_s, bb_low_s = compute_bollinger(s_close, window=20)
        bb_up = bb_up_s.to_numpy()
        bb_low = bb_low_s.to_numpy()
        low_n = s_low.rolling(stoch_period, min_periods=stoch_period).min()
        high_n = s_high.rolling(stoch_period, min_periods=stoch_period).max()
        stoch_k_s = ((s_close - low_n) / (high_n - low_n).replace(0, np.nan) * 100.0).fillna(50.0)
        stoch_d_s = stoch_k_s.rolling(3, min_periods=1).mean()
        stoch_k = stoch_k_s.to_numpy()
        stoch_d = stoch_d_s.to_numpy()
        adx = compute_adx(s_high, s_low, s_close, period=14).to_numpy()
        ema_fast = ema(s_close, span=ema_fast_n).to_numpy()
        ema_slow = ema(s_close, span=ema_slow_n).to_numpy()

    vol_avg = pd.Series(volume).rolling(20, min_periods=5).mean().ffill().fillna(0.0).to_numpy()
    return {
        "close": close,
        "high": high,
        "low": low,
        "volume": volume,
        "volume_avg": vol_avg,
        "rsi": np.nan_to_num(rsi, nan=50.0),
        "macd": np.nan_to_num(macd, nan=0.0),
        "macd_signal": np.nan_to_num(macd_signal, nan=0.0),
        "bb_upper": np.nan_to_num(bb_up, nan=close),
        "bb_lower": np.nan_to_num(bb_low, nan=close),
        "stoch_k": np.nan_to_num(stoch_k, nan=50.0),
        "stoch_d": np.nan_to_num(stoch_d, nan=50.0),
        "adx": np.nan_to_num(adx, nan=0.0),
        "ema_fast": np.nan_to_num(ema_fast, nan=close),
        "ema_slow": np.nan_to_num(ema_slow, nan=close),
    }


def _vote_rows(arr: dict[str, np.ndarray]) -> list[IndicatorVote]:
    if len(arr["close"]) < 3:
        return []
    i = -1
    i_prev = -2
    close = float(arr["close"][i])
    close_prev = float(arr["close"][i_prev])
    adx = float(arr["adx"][i])
    adx_ok = adx > 25.0

    rows: list[IndicatorVote] = []

    rsi = float(arr["rsi"][i])
    rsi_prev = float(arr["rsi"][i_prev])
    rsi_fire = rsi_prev < 30.0 and rsi >= 30.0
    rsi_bear = rsi_prev > 70.0 and rsi <= 70.0
    rsi_vote = 1 if rsi_fire else -1 if rsi_bear else 0
    rows.append(
        IndicatorVote(
            name="rsi_crossback",
            value=rsi,
            vote=rsi_vote,
            weight=INDICATOR_WEIGHTS["rsi_crossback"],
            fired_rule="RSI crossed above 30 (bull) / below 70 (bear)",
            explanation=f"RSI moved {rsi_prev:.2f} -> {rsi:.2f}; bull={rsi_fire}, bear={rsi_bear}.",
        )
    )

    macd = float(arr["macd"][i])
    macd_prev = float(arr["macd"][i_prev])
    macd_sig = float(arr["macd_signal"][i])
    macd_sig_prev = float(arr["macd_signal"][i_prev])
    macd_bull_raw = macd_prev <= macd_sig_prev and macd > macd_sig
    macd_bear_raw = macd_prev >= macd_sig_prev and macd < macd_sig
    macd_vote = 1 if (macd_bull_raw and adx_ok) else -1 if (macd_bear_raw and adx_ok) else 0
    rows.append(
        IndicatorVote(
            name="macd_cross",
            value=macd - macd_sig,
            vote=macd_vote,
            weight=INDICATOR_WEIGHTS["macd_cross"],
            fired_rule="MACD cross with ADX gate (+ bull / - bear)",
            explanation=f"MACD {macd:.4f} vs signal {macd_sig:.4f}; bull={macd_bull_raw}, bear={macd_bear_raw}, ADX gate={adx_ok}.",
        )
    )

    ema_fast = float(arr["ema_fast"][i])
    ema_fast_prev = float(arr["ema_fast"][i_prev])
    ema_slow = float(arr["ema_slow"][i])
    ema_slow_prev = float(arr["ema_slow"][i_prev])
    ema_bull_raw = ema_fast_prev <= ema_slow_prev and ema_fast > ema_slow
    ema_bear_raw = ema_fast_prev >= ema_slow_prev and ema_fast < ema_slow
    ema_vote = 1 if (ema_bull_raw and adx_ok) else -1 if (ema_bear_raw and adx_ok) else 0
    rows.append(
        IndicatorVote(
            name="ema_cross",
            value=ema_fast - ema_slow,
            vote=ema_vote,
            weight=INDICATOR_WEIGHTS["ema_cross"],
            fired_rule="EMA cross with ADX gate (+ bull / - bear)",
            explanation=f"EMA fast {ema_fast:.2f} vs slow {ema_slow:.2f}; bull={ema_bull_raw}, bear={ema_bear_raw}, ADX gate={adx_ok}.",
        )
    )

    bb_low = float(arr["bb_lower"][i])
    bb_tag_prev = close_prev <= float(arr["bb_lower"][i_prev]) * 1.002
    bb_reclaim = close > bb_low and rsi < 35.0 and bb_tag_prev
    bb_upper = float(arr["bb_upper"][i])
    bb_reject = close < bb_upper and rsi > 65.0 and close_prev >= float(arr["bb_upper"][i_prev]) * 0.998
    bb_vote = 1 if bb_reclaim else -1 if bb_reject else 0
    rows.append(
        IndicatorVote(
            name="bollinger_reclaim",
            value=close - bb_low,
            vote=bb_vote,
            weight=INDICATOR_WEIGHTS["bollinger_reclaim"],
            fired_rule="Bollinger reclaim/reject (+ lower reclaim, - upper reject)",
            explanation=f"Close {close:.2f}, lower {bb_low:.2f}, upper {bb_upper:.2f}, RSI {rsi:.2f}; bull={bb_reclaim}, bear={bb_reject}.",
        )
    )

    stoch_k = float(arr["stoch_k"][i])
    stoch_k_prev = float(arr["stoch_k"][i_prev])
    stoch_d = float(arr["stoch_d"][i])
    stoch_d_prev = float(arr["stoch_d"][i_prev])
    stoch_bull = stoch_k_prev <= stoch_d_prev and stoch_k > stoch_d and min(stoch_k, stoch_d) < 20.0
    stoch_bear = stoch_k_prev >= stoch_d_prev and stoch_k < stoch_d and max(stoch_k, stoch_d) > 80.0
    stoch_vote = 1 if stoch_bull else -1 if stoch_bear else 0
    rows.append(
        IndicatorVote(
            name="stoch_oversold_cross",
            value=stoch_k - stoch_d,
            vote=stoch_vote,
            weight=INDICATOR_WEIGHTS["stoch_oversold_cross"],
            fired_rule="Stoch cross (+ oversold bull / - overbought bear)",
            explanation=f"Stoch K {stoch_k:.2f}, D {stoch_d:.2f}; bull={stoch_bull}, bear={stoch_bear}.",
        )
    )

    vol = float(arr["volume"][i])
    vol_avg = float(arr["volume_avg"][i] or 0.0)
    vol_bull_raw = vol_avg > 0 and vol > 1.5 * vol_avg and close > close_prev
    vol_bear_raw = vol_avg > 0 and vol > 1.5 * vol_avg and close < close_prev
    vol_vote = 1 if (vol_bull_raw and adx_ok) else -1 if (vol_bear_raw and adx_ok) else 0
    rows.append(
        IndicatorVote(
            name="volume_confirmed_up",
            value=(vol / vol_avg) if vol_avg > 0 else 0.0,
            vote=vol_vote,
            weight=INDICATOR_WEIGHTS["volume_confirmed_up"],
            fired_rule="Volume impulse with ADX gate (+ up move / - down move)",
            explanation=f"Volume {vol:.0f} vs avg {vol_avg:.0f}; up={vol_bull_raw}, down={vol_bear_raw}, ADX gate={adx_ok}.",
        )
    )

    rows.append(
        IndicatorVote(
            name="adx_gate",
            value=adx,
            vote=1 if adx_ok else 0,
            weight=INDICATOR_WEIGHTS["adx_gate"],
            fired_rule="ADX > 25 trend-quality gate",
            explanation=f"ADX is {adx:.2f}; trend-quality gate is {'open' if adx_ok else 'closed'}.",
        )
    )

    return rows


def _score(votes: list[IndicatorVote]) -> tuple[float, float]:
    if not votes:
        return 0.0, 0.0
    total_w = float(sum(v.weight for v in votes))
    raw = 0.0
    for v in votes:
        if v.name in TREND_SIGNALS:
            raw += float(v.vote) * v.weight
        elif v.name == "adx_gate":
            raw += (1.0 if v.vote > 0 else -1.0) * v.weight
        else:
            raw += float(v.vote) * v.weight
    score = raw / total_w if total_w > 0 else 0.0
    confidence = min(1.0, max(0.0, sum(v.weight for v in votes if v.vote != 0) / total_w if total_w else 0.0))
    return float(score), float(confidence)


async def compute_technical(
    *,
    db: AsyncSession,
    market_data,
    redis_client,
    ticker: str,
    horizon: str,
) -> dict[str, Any]:
    symbol = ticker.upper()
    h = (horizon or "short").lower()
    if h not in HORIZON_MARKET_FETCH:
        h = "short"
    cache_key = f"signals:{symbol}:{h}:technical"
    lock_key = f"{cache_key}:lock"
    ttl = _cache_ttl(h)

    if redis_client is not None:
        cached = await redis_client.get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass

    lock_acquired = False
    if redis_client is not None:
        try:
            lock_acquired = bool(await redis_client.set(lock_key, "1", ex=15, nx=True))
            if not lock_acquired:
                await asyncio.sleep(0.1)
                cached = await redis_client.get(cache_key)
                if cached:
                    return json.loads(cached)
        except Exception:
            lock_acquired = False

    fetch_cfg = HORIZON_MARKET_FETCH[h]
    bars_payload = await market_data.get_bars(symbol, fetch_cfg["span"], tf=fetch_cfg["tf"])
    rows = bars_payload.get("bars") or []
    df = _series_from_rows(rows)
    df = _trim_lookback(df, int(fetch_cfg["lookback_days"]))
    min_bars = _minimum_bars(h)
    if len(df) < min_bars and h == "long":
        fallback_cfg = HORIZON_MARKET_FETCH["mid"]
        fallback_payload = await market_data.get_bars(symbol, fallback_cfg["span"], tf=fallback_cfg["tf"])
        fallback_df = _trim_lookback(_series_from_rows(fallback_payload.get("bars") or []), int(fallback_cfg["lookback_days"]))
        if len(fallback_df) >= _minimum_bars("mid"):
            logger.debug("signals technical fallback: ticker=%s horizon=%s -> mid bar_count=%s", symbol, h, len(fallback_df))
            df = fallback_df
            bars_payload = fallback_payload
            h = "mid"
            fetch_cfg = fallback_cfg
            min_bars = _minimum_bars(h)

    if len(df) < min_bars:
        payload = {
            "ticker": symbol,
            "horizon": h,
            "track": "technical",
            "status": "insufficient_data",
            "action": "neutral",
            "score": 0.0,
            "confidence": 0.0,
            "indicators": [],
            "triggered_rules": [],
            "explanation": f"Insufficient data: need at least {min_bars} bars, received {len(df)}.",
            "as_of": datetime.utcnow().isoformat(),
        }
        if redis_client is not None:
            await redis_client.set(cache_key, json.dumps(payload), ex=ttl)
            if lock_acquired:
                await redis_client.delete(lock_key)
        return payload

    arr = _talib_or_fallback(df, h)
    votes = _vote_rows(arr)
    score, confidence = _score(votes)
    indicators = [asdict(v) for v in votes]
    triggered_rules = [
        f"{'+' if int(v['vote']) > 0 else '-'}{v['name']}"
        for v in indicators
        if int(v["vote"]) != 0
    ]
    action = "bullish" if score > 0.2 else "bearish" if score < -0.2 else "neutral"
    indicator_debug = ", ".join(
        f"{v['name']}={float(v['value']):.4f}:{int(v['vote'])}" for v in indicators
    )
    logger.debug(
        "signals technical compute: ticker=%s horizon=%s bar_count=%s min_bars=%s params=%s indicators=[%s]",
        symbol,
        h,
        len(df),
        min_bars,
        params_for(h),
        indicator_debug,
    )
    explanation = (
        f"{symbol} technical model ({h}) score {score:.3f}. "
        f"Triggered rules: {', '.join(triggered_rules) if triggered_rules else 'none'}."
    )

    payload = {
        "ticker": symbol,
        "horizon": h,
        "track": "technical",
        "status": "ok",
        "action": action,
        "score": round(score, 6),
        "confidence": round(confidence, 6),
        "indicators": indicators,
        "triggered_rules": triggered_rules,
        "explanation": explanation,
        "source": bars_payload.get("source", ""),
        "as_of": datetime.utcnow().isoformat(),
    }

    if redis_client is not None:
        await redis_client.set(cache_key, json.dumps(payload), ex=ttl)
        if lock_acquired:
            await redis_client.delete(lock_key)
    return payload
