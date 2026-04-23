import numpy as np
import pandas as pd


def compute_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    delta = prices.diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)

    gain_series = pd.Series(gain, index=prices.index)
    loss_series = pd.Series(loss, index=prices.index)

    avg_gain = gain_series.rolling(window=period, min_periods=period).mean()
    avg_loss = loss_series.rolling(window=period, min_periods=period).mean()

    rs = avg_gain / (avg_loss.replace(0, np.nan))
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def ema(values: pd.Series, span: int) -> pd.Series:
    return values.ewm(span=span, adjust=False).mean()


def compute_macd(prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series]:
    fast_ema = ema(prices, fast)
    slow_ema = ema(prices, slow)
    macd_line = fast_ema - slow_ema
    signal_line = ema(macd_line, signal)
    return macd_line.fillna(0.0), signal_line.fillna(0.0)


def compute_bollinger(prices: pd.Series, window: int = 20, num_std: float = 2.0) -> tuple[pd.Series, pd.Series]:
    mean = prices.rolling(window=window, min_periods=window).mean()
    std = prices.rolling(window=window, min_periods=window).std(ddof=0)
    upper = mean + num_std * std
    lower = mean - num_std * std
    return upper.fillna(prices), lower.fillna(prices)


def compute_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    tr1 = (high - low).abs()
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.rolling(window=period, min_periods=period).mean()
    plus_di = 100 * (plus_dm.rolling(window=period, min_periods=period).mean() / atr.replace(0, np.nan))
    minus_di = 100 * (minus_dm.rolling(window=period, min_periods=period).mean() / atr.replace(0, np.nan))
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)) * 100
    adx = dx.rolling(window=period, min_periods=period).mean()
    return adx.fillna(0.0)


def compute_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff().fillna(0.0))
    step = np.where(direction > 0, volume, np.where(direction < 0, -volume, 0.0))
    obv = pd.Series(step, index=close.index).cumsum()
    return obv.fillna(0.0)


def compute_vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    typical = (high + low + close) / 3.0
    cum_tpv = (typical * volume).cumsum()
    cum_vol = volume.cumsum().replace(0, np.nan)
    return (cum_tpv / cum_vol).fillna(close)


def compute_roc(prices: pd.Series, period: int = 5) -> pd.Series:
    shifted = prices.shift(period)
    roc = ((prices / shifted) - 1.0) * 100.0
    return roc.fillna(0.0)
