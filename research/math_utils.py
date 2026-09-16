"""Self-contained indicator math for the research module.

Deliberately does NOT import from `src/indicators.py` — research/ has zero
coupling to production. Same primitives, same defaults; if a divergence is
ever spotted it's a bug to reconcile, not tolerate.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


# ---------------------------------------------------------------- moving avgs
def ema(closes: pd.Series, period: int) -> pd.Series:
    return closes.ewm(span=period, adjust=False).mean()


def ema_stack_up(closes: pd.Series, periods: tuple[int, int, int] = (9, 21, 50)) -> pd.Series:
    e = [ema(closes, p) for p in periods]
    return (e[0] > e[1]) & (e[1] > e[2])


def ema_stack_down(closes: pd.Series, periods: tuple[int, int, int] = (9, 21, 50)) -> pd.Series:
    e = [ema(closes, p) for p in periods]
    return (e[0] < e[1]) & (e[1] < e[2])


# ---------------------------------------------------------------- volatility
def true_range(df: pd.DataFrame) -> pd.Series:
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift(1)).abs()
    lc = (df["low"] - df["close"].shift(1)).abs()
    return pd.concat([hl, hc, lc], axis=1).max(axis=1)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    return true_range(df).rolling(period).mean()


def bollinger_width(closes: pd.Series, period: int = 20, num_std: float = 2.0) -> pd.Series:
    mean = closes.rolling(period).mean()
    std = closes.rolling(period).std()
    return (mean + num_std * std - (mean - num_std * std)) / mean.replace(0, np.nan)


def bb_width_percentile(closes: pd.Series, period: int = 20, lookback: int = 60) -> pd.Series:
    """Percentile rank of current BB width within trailing `lookback` bars.
    0.0 = tightest ever in window; 1.0 = widest. Uses only past bars per row.

    Implementation note: `.iloc[-1]` (positional) not `x[-1]` — pandas Series
    with a DatetimeIndex treat `x[-1]` as a label lookup, which raises KeyError.
    """
    w = bollinger_width(closes, period)

    def _pct(x: pd.Series) -> float:
        last = x.iloc[-1]
        if not pd.notna(last):
            return float("nan")
        return float((x < last).sum() / max(len(x) - 1, 1))

    return w.rolling(lookback).apply(_pct, raw=False)


def atr_ratio(df: pd.DataFrame, period: int = 14, lookback: int = 60) -> pd.Series:
    """Current ATR ÷ rolling mean of ATR over `lookback` bars."""
    a = atr(df, period)
    return a / a.rolling(lookback).mean().replace(0, np.nan)


# ---------------------------------------------------------------- MACD
def macd(closes: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    ef = ema(closes, fast)
    es = ema(closes, slow)
    line = ef - es
    sig = line.ewm(span=signal, adjust=False).mean()
    hist = line - sig
    return pd.DataFrame({"macd_line": line, "signal": sig, "hist": hist})


def macd_transition(closes: pd.Series, within: int = 3) -> pd.Series:
    """String label per bar: 'cross_up', 'cross_down', 'accel_up', 'accel_down', 'none'.

    'cross_up' / 'cross_down' — histogram sign change within the last `within` bars.
    'accel_up' / 'accel_down' — same sign but abs(hist) rising for last 2 bars.
    """
    m = macd(closes)
    h = m["hist"]
    hp = h.shift(1)
    sign = np.sign(h.fillna(0)).astype(int)
    sign_prev = np.sign(hp.fillna(0)).astype(int)
    # Cross in this bar: current sign different from previous, current nonzero
    cross_this_bar = (sign != sign_prev) & (sign != 0)
    # Cross within last `within` bars
    cross_up = cross_this_bar & (sign > 0)
    cross_dn = cross_this_bar & (sign < 0)
    cross_up_recent = cross_up.rolling(within).max().astype(bool)
    cross_dn_recent = cross_dn.rolling(within).max().astype(bool)
    # Acceleration: same sign as prev bar AND |h| > |h_{-1}| AND same sign 2 bars back
    same_sign_2 = (sign == sign_prev) & (sign_prev == np.sign(h.shift(2).fillna(0)).astype(int))
    accel = same_sign_2 & (h.abs() > hp.abs())
    accel_up = accel & (sign > 0)
    accel_dn = accel & (sign < 0)

    out = pd.Series("none", index=closes.index)
    out = out.mask(accel_dn, "accel_down")
    out = out.mask(accel_up, "accel_up")
    out = out.mask(cross_dn_recent, "cross_down")
    out = out.mask(cross_up_recent, "cross_up")
    return out


# ---------------------------------------------------------------- pivots
def fractal_pivots(df: pd.DataFrame, order: int = 3) -> tuple[pd.Series, pd.Series]:
    """Returns two boolean Series (pivot_high, pivot_low). A bar at index i is a
    pivot high iff its high is the max of window [i-order, i+order]. Since this
    requires future bars, the pivot flag is ANCHORED at i but only becomes
    KNOWN at bar i+order. `is_known_at(t)` masks a pivot flag by that latency."""
    highs = df["high"]
    lows = df["low"]
    n = len(df)
    ph = pd.Series(False, index=df.index)
    pl = pd.Series(False, index=df.index)
    for i in range(order, n - order):
        window_h = highs.iloc[i - order : i + order + 1]
        window_l = lows.iloc[i - order : i + order + 1]
        if highs.iloc[i] == window_h.max():
            ph.iloc[i] = True
        if lows.iloc[i] == window_l.min():
            pl.iloc[i] = True
    return ph, pl


def is_known_at(pivot_flags: pd.Series, order: int) -> pd.Series:
    """A pivot at bar i is only KNOWN at bar i+order (needs order future bars).
    Shifts the pivot flag forward by `order` bars to enforce no-lookahead."""
    return pivot_flags.shift(order).fillna(False).astype(bool)


def last_pivot_above(df: pd.DataFrame, up_to_index: int, order: int = 3,
                     lookback: int = 60) -> float | None:
    """Highest known pivot high BEFORE or AT bar `up_to_index`, within trailing
    `lookback`. Uses is_known_at so no lookahead."""
    ph, _ = fractal_pivots(df.iloc[max(0, up_to_index - lookback - order): up_to_index + 1], order)
    known = is_known_at(ph, order)
    piv_prices = df["high"].iloc[max(0, up_to_index - lookback - order): up_to_index + 1][known]
    if piv_prices.empty:
        return None
    return float(piv_prices.max())


def last_pivot_below(df: pd.DataFrame, up_to_index: int, order: int = 3,
                     lookback: int = 60) -> float | None:
    _, pl = fractal_pivots(df.iloc[max(0, up_to_index - lookback - order): up_to_index + 1], order)
    known = is_known_at(pl, order)
    piv_prices = df["low"].iloc[max(0, up_to_index - lookback - order): up_to_index + 1][known]
    if piv_prices.empty:
        return None
    return float(piv_prices.min())
