"""
Shared indicator + microstructure helpers used by the technical analyzer.

Kept dependency-light (pandas/numpy only) so every edge in the confidence
stack computes from the same primitives.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

Pivot = tuple[Any, float]


def rsi(closes: pd.Series, period: int = 14) -> float:
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    series = 100 - (100 / (1 + rs))
    value = series.iloc[-1]
    return float(value) if pd.notna(value) else 50.0


def sma(closes: pd.Series, period: int) -> Optional[float]:
    if len(closes) < period:
        return None
    value = closes.rolling(period).mean().iloc[-1]
    return float(value) if pd.notna(value) else None


def ema(closes: pd.Series, period: int) -> Optional[float]:
    """Latest exponential moving average."""
    if len(closes) < period:
        return None
    value = closes.ewm(span=period, adjust=False).mean().iloc[-1]
    return float(value) if pd.notna(value) else None


def ema_alignment(closes: pd.Series, fast: int, slow: int, direction: str = "up") -> Optional[bool]:
    """Is the fast EMA above (up) / below (down) the slow EMA? Used for the
    9/21 (intraday timing), 20/50 (swing trend) and 50/200 (backdrop = the
    golden/death cross) EMA reads that feed the single capped momentum
    dimension. Returns None when there isn't enough history to judge."""
    ef, es = ema(closes, fast), ema(closes, slow)
    if ef is None or es is None:
        return None
    return ef > es if direction == "up" else ef < es


def mfi(df: pd.DataFrame, period: int = 14) -> float:
    """Money Flow Index -- the volume-weighted RSI. Uses typical price x
    volume, splitting money flow into up-days vs down-days over `period`.
    Replaces RSI everywhere (user does not trade off RSI). 0-100; ~50 neutral,
    >80 overbought, <20 oversold. Falls back to 50.0 without enough data."""
    need = {"High", "Low", "Close", "Volume"}
    if df is None or df.empty or not need.issubset(df.columns) or len(df) <= period:
        return 50.0
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    money_flow = typical * df["Volume"]
    delta = typical.diff()
    pos = money_flow.where(delta > 0, 0.0)
    neg = money_flow.where(delta < 0, 0.0)
    pos_sum = pos.rolling(period).sum()
    neg_sum = neg.rolling(period).sum()
    ratio = pos_sum / neg_sum.replace(0, np.nan)
    value = (100 - 100 / (1 + ratio)).iloc[-1]
    return float(value) if pd.notna(value) else 50.0


def relative_strength(closes: pd.Series, bench_closes: pd.Series,
                      period: int = 20) -> Optional[float]:
    """Relative strength vs a benchmark (SPY): symbol %-return minus
    benchmark %-return over `period` bars. Positive = outperforming the
    market. This is the scored RS edge (independent signal) + a logged field
    whose correlation with wins the feedback review surfaces."""
    r_sym = roc(closes, period)
    r_ben = roc(bench_closes, period)
    if r_sym is None or r_ben is None:
        return None
    return round(r_sym - r_ben, 2)


def roc(closes: pd.Series, period: int) -> Optional[float]:
    """Rate of change (%) over `period` bars."""
    if len(closes) <= period:
        return None
    past = closes.iloc[-period - 1]
    if past == 0:
        return None
    return float((closes.iloc[-1] - past) / past * 100)


def macd(closes: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, Any]:
    ema_fast = closes.ewm(span=fast, adjust=False).mean()
    ema_slow = closes.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    if len(macd_line) < 2:
        return {"signal": "NEUTRAL", "histogram": 0.0}
    m_now, m_prev = macd_line.iloc[-1], macd_line.iloc[-2]
    s_now, s_prev = signal_line.iloc[-1], signal_line.iloc[-2]
    if m_now > s_now and m_prev <= s_prev:
        state = "BULLISH_CROSSOVER"
    elif m_now < s_now and m_prev >= s_prev:
        state = "BEARISH_CROSSOVER"
    elif m_now > s_now:
        state = "BULLISH"
    else:
        state = "BEARISH"
    return {"signal": state, "histogram": float(m_now - s_now)}


def true_range(df: pd.DataFrame) -> pd.Series:
    """Wilder's true range -- the per-bar building block for ATR/Keltner."""
    prev_close = df["Close"].shift(1)
    spans = pd.concat([df["High"] - df["Low"],
                       (df["High"] - prev_close).abs(),
                       (df["Low"] - prev_close).abs()], axis=1)
    return spans.max(axis=1)


def atr_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ATR as a series (Wilder smoothing) -- callers that only want the last
    value should use `atr`."""
    return true_range(df).ewm(alpha=1.0 / period, adjust=False).mean()


def atr(df: pd.DataFrame, period: int = 14) -> Optional[float]:
    series = atr_series(df, period).dropna()
    return float(series.iloc[-1]) if len(series) else None


def bollinger_series(closes: pd.Series, period: int = 20,
                     num_std: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    """(upper, middle, lower) Bollinger bands as full series."""
    middle = closes.rolling(period).mean()
    std = closes.rolling(period).std()
    return middle + num_std * std, middle, middle - num_std * std


def keltner_series(df: pd.DataFrame, period: int = 20, atr_mult: float = 1.5,
                   atr_period: int = 20) -> tuple[pd.Series, pd.Series, pd.Series]:
    """(upper, middle, lower) Keltner channels -- an EMA basis with ATR bands.

    Pairing these with Bollinger bands is what makes a squeeze measurable: BB
    width is standard-deviation-driven, Keltner width is range-driven, so
    Bollinger bands contracting INSIDE Keltner means realised volatility has
    collapsed relative to the recent trading range (the TTM squeeze).
    """
    middle = df["Close"].ewm(span=period, adjust=False).mean()
    band = atr_series(df, atr_period) * atr_mult
    return middle + band, middle, middle - band


def bandwidth_series(closes: pd.Series, period: int = 20,
                     num_std: float = 2.0) -> pd.Series:
    """Bollinger bandwidth: band span as a fraction of the basis. Normalised by
    the basis so it is comparable across symbols and price levels."""
    upper, middle, lower = bollinger_series(closes, period, num_std)
    return (upper - lower) / middle.replace(0, np.nan)


def percentile_rank(series: pd.Series, value: float) -> Optional[float]:
    """Share of `series` (0-100) sitting strictly below `value`."""
    clean = series.dropna()
    if len(clean) < 2 or pd.isna(value):
        return None
    return float((clean < value).mean() * 100.0)


def bollinger_bands(closes: pd.Series, period: int = 20, num_std: float = 2.0,
                    squeeze_lookback: int = 250,
                    squeeze_pctile: float = 10.0) -> dict[str, Any]:
    """Bollinger read including the basis (middle band) and a bandwidth
    PERCENTILE rank rather than a crude quartile test.

    The old test flagged a squeeze whenever width sat in the lowest quartile of
    60 bars -- true ~25% of the time by construction, so it tagged ordinary
    quiet as compression. Ranking current bandwidth against `squeeze_lookback`
    bars and demanding the lowest `squeeze_pctile`% makes the flag mean
    "unusually compressed for THIS name" instead of merely "below average".
    """
    upper, middle, lower = bollinger_series(closes, period, num_std)
    last_close = closes.iloc[-1]
    last_upper, last_lower, last_mean = upper.iloc[-1], lower.iloc[-1], middle.iloc[-1]
    if pd.isna(last_upper) or pd.isna(last_lower) or last_upper == last_lower:
        return {"percent_b": 0.5, "position": "MIDDLE", "upper": None, "lower": None,
                "middle": None, "breakout": False, "breakdown": False, "squeeze": False,
                "bandwidth": None, "bandwidth_pctile": None, "squeeze_bars": 0}
    percent_b = (last_close - last_lower) / (last_upper - last_lower)
    if percent_b <= 0.15:
        position = "NEAR_LOWER"
    elif percent_b >= 0.85:
        position = "NEAR_UPPER"
    else:
        position = "MIDDLE"

    width = (upper - lower) / middle.replace(0, np.nan)
    current_width = width.iloc[-1]
    history = width.tail(squeeze_lookback)
    pctile = percentile_rank(history, current_width)
    # enough history to rank against, and tighter than all but `squeeze_pctile`%
    enough = history.dropna().shape[0] >= max(20, period)
    squeeze = bool(enough and pctile is not None and pctile <= squeeze_pctile)

    # How long the compression has been running -- a coil is not a single quiet
    # bar. Judged against one threshold taken from the lookback window, not a
    # rolling one: a rolling threshold sinks as the coil's own bars fill the low
    # end of the window, which resets the count on exactly the long coils that
    # matter most. `src.compression` measures this off BB-inside-Keltner, which
    # is steadier still.
    squeeze_bars = 0
    if pd.notna(threshold := history.quantile(squeeze_pctile / 100.0)):
        for value in reversed(width.tolist()):
            if pd.isna(value) or value > threshold:
                break
            squeeze_bars += 1

    return {"percent_b": float(percent_b), "position": position,
            "upper": float(last_upper), "lower": float(last_lower),
            "middle": float(last_mean) if pd.notna(last_mean) else None,
            "breakout": bool(last_close > last_upper),
            "breakdown": bool(last_close < last_lower),
            "squeeze": squeeze,
            "bandwidth": float(current_width) if pd.notna(current_width) else None,
            "bandwidth_pctile": round(pctile, 1) if pctile is not None else None,
            "squeeze_bars": int(squeeze_bars)}


def find_pivots(df: pd.DataFrame, order: int = 3) -> tuple[list[Pivot], list[Pivot]]:
    """Fractal swing highs (supply) / lows (demand)."""
    highs, lows = df["High"], df["Low"]
    n = len(df)
    pivot_highs: list[Pivot] = []
    pivot_lows: list[Pivot] = []
    for i in range(order, n - order):
        if highs.iloc[i] == highs.iloc[i - order: i + order + 1].max():
            pivot_highs.append((df.index[i], float(highs.iloc[i])))
        if lows.iloc[i] == lows.iloc[i - order: i + order + 1].min():
            pivot_lows.append((df.index[i], float(lows.iloc[i])))
    return pivot_highs, pivot_lows


def structure_bias(pivot_highs: list[Pivot], pivot_lows: list[Pivot]) -> str:
    """HH/HL -> BULLISH, LH/LL -> BEARISH, else NEUTRAL."""
    if len(pivot_highs) < 2 or len(pivot_lows) < 2:
        return "NEUTRAL"
    hs = [p[1] for p in pivot_highs[-3:]]
    ls = [p[1] for p in pivot_lows[-3:]]
    highs_rising = all(a < b for a, b in zip(hs, hs[1:]))
    highs_falling = all(a > b for a, b in zip(hs, hs[1:]))
    lows_rising = all(a < b for a, b in zip(ls, ls[1:]))
    lows_falling = all(a > b for a, b in zip(ls, ls[1:]))
    if highs_rising and lows_rising:
        return "BULLISH"
    if highs_falling and lows_falling:
        return "BEARISH"
    return "NEUTRAL"


def nearest_level(pivots: list[Pivot], price: float, direction: str) -> Optional[float]:
    candidates = [p[1] for p in pivots if (p[1] < price if direction == "below" else p[1] > price)]
    if not candidates:
        return None
    return max(candidates) if direction == "below" else min(candidates)


def volume_profile(df: pd.DataFrame, bins: int = 24, value_area_pct: float = 0.70) -> dict[str, Any]:
    """Volume-at-price histogram.

    Distributes each bar's volume across a price bin (using the bar's
    typical price) to find the Point of Control (POC, the most-traded
    price = strongest support/resistance) and the Value Area (the price
    band containing `value_area_pct` of volume). High-volume nodes are
    where price previously transacted heavily -- a level it rejected from
    and later reclaimed tends to flip from resistance to support.
    """
    if df.empty or len(df) < 5:
        return {"poc": None, "value_area_low": None, "value_area_high": None, "hvns": []}
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    lo, hi = float(typical.min()), float(typical.max())
    if hi <= lo:
        return {"poc": None, "value_area_low": None, "value_area_high": None, "hvns": []}
    edges = np.linspace(lo, hi, bins + 1)
    centers = (edges[:-1] + edges[1:]) / 2
    vol_at_price = np.zeros(bins)
    idx = np.clip(np.digitize(typical.values, edges) - 1, 0, bins - 1)
    for i, v in zip(idx, df["Volume"].values):
        vol_at_price[i] += float(v)

    poc_bin = int(np.argmax(vol_at_price))
    poc = float(centers[poc_bin])

    # Grow the value area outward from the POC until it holds value_area_pct.
    total = vol_at_price.sum()
    target = total * value_area_pct
    included = {poc_bin}
    running = vol_at_price[poc_bin]
    lo_i = hi_i = poc_bin
    while running < target and (lo_i > 0 or hi_i < bins - 1):
        down = vol_at_price[lo_i - 1] if lo_i > 0 else -1
        up = vol_at_price[hi_i + 1] if hi_i < bins - 1 else -1
        if up >= down:
            hi_i += 1
            included.add(hi_i)
            running += vol_at_price[hi_i]
        else:
            lo_i -= 1
            included.add(lo_i)
            running += vol_at_price[lo_i]

    # High-volume nodes: bins in the top 20% of volume.
    threshold = vol_at_price.max() * 0.6
    hvns = sorted(float(centers[i]) for i in range(bins) if vol_at_price[i] >= threshold)
    return {
        "poc": round(poc, 4),
        "value_area_low": round(float(centers[min(included)]), 4),
        "value_area_high": round(float(centers[max(included)]), 4),
        "hvns": [round(h, 4) for h in hvns],
    }
