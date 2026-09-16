"""MACD momentum — raw fields + state, no bullish/bearish "verdict".

Preregistered 12/26/9 EMA MACD. All slopes are 3-bar finite differences.
Below `_MIN_BARS = 38` (26 slow EMA + 9 signal EMA + 3 for slope), fields
return None / "UNAVAILABLE". See PREREGISTRATION.md § 5.

Correlation note (preregistered): all fields here belong to the MACD
family — they share one 12/26/9 EMA computation and MUST NOT be counted
as independent confirmations.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import math_utils as mu


FEATURE_VERSION = "v0.3.0"

_MIN_BARS = 38
_NEUTRAL_HIST_ATR_MULT = 0.05


def _num(x: float) -> float | None:
    return float(x) if np.isfinite(x) else None


def context_at(df: pd.DataFrame, t: int) -> dict:
    """Compute MACD context at close of bar t.

    df must have a 'close' column. ATR14 is computed on df[:t+1] for the
    neutral-band test; caller does not need to pass it.
    """
    if t < 0 or t >= len(df):
        raise IndexError(f"t={t} out of range for df of length {len(df)}")
    hist = df.iloc[: t + 1]

    if len(hist) < _MIN_BARS:
        return _unavailable(hist)

    close = hist["close"]
    m = mu.macd(close)
    line = m["macd_line"]
    signal = m["signal"]
    histseries = m["hist"]

    if pd.isna(line.iloc[-1]) or pd.isna(signal.iloc[-1]) or pd.isna(histseries.iloc[-1]):
        return _unavailable(hist)

    macd_line_t = float(line.iloc[-1])
    macd_signal_t = float(signal.iloc[-1])
    macd_hist_t = float(histseries.iloc[-1])

    # 3-bar finite-difference slopes
    def _slope(series: pd.Series) -> float:
        if len(series) < 4:
            return float("nan")
        past = series.iloc[-4]
        cur = series.iloc[-1]
        if not (pd.notna(past) and pd.notna(cur)):
            return float("nan")
        return float((cur - past) / 3.0)

    line_slope = _slope(line)
    signal_slope = _slope(signal)
    hist_slope = _slope(histseries)

    # Acceleration: change of slope over 3 bars
    if len(histseries) >= 7:
        past_hist_slope = float((histseries.iloc[-4] - histseries.iloc[-7]) / 3.0) \
            if pd.notna(histseries.iloc[-4]) and pd.notna(histseries.iloc[-7]) else float("nan")
        hist_accel = hist_slope - past_hist_slope if np.isfinite(past_hist_slope) and np.isfinite(hist_slope) else float("nan")
    else:
        hist_accel = float("nan")

    # Cross detection (histogram sign flips)
    sign = np.sign(histseries.fillna(0)).astype(int)
    flips = (sign != sign.shift(1)) & (sign != 0)
    flip_idx = np.where(flips.tail(250).to_numpy())[0]
    if len(flip_idx):
        last_flip_local = flip_idx[-1]
        bars_since_cross = int((len(flips.tail(250)) - 1) - last_flip_local)
        cross_direction = "up" if sign.tail(250).iloc[last_flip_local] > 0 else "down"
    else:
        bars_since_cross = None
        cross_direction = "none"

    # ATR14 for the neutral-band test
    atr14 = mu.atr(hist, 14)
    atr_t = float(atr14.iloc[-1]) if len(atr14) and pd.notna(atr14.iloc[-1]) else float("nan")

    # State classification
    state = _state(macd_hist_t, hist_slope, atr_t)

    return {
        "momentum._feature_version": FEATURE_VERSION,
        "momentum._source_timeframe": "1d",
        "momentum._known_at": hist.index[-1].isoformat(),
        "momentum._availability": True,
        "momentum.macd_line": macd_line_t,
        "momentum.macd_signal": macd_signal_t,
        "momentum.macd_hist": macd_hist_t,
        "momentum.macd_line_slope": _num(line_slope),
        "momentum.macd_signal_slope": _num(signal_slope),
        "momentum.macd_hist_slope": _num(hist_slope),
        "momentum.macd_hist_acceleration": _num(hist_accel),
        "momentum.macd_above_zero": bool(macd_line_t > 0),
        "momentum.macd_below_zero": bool(macd_line_t < 0),
        "momentum.macd_above_signal": bool(macd_line_t > macd_signal_t),
        "momentum.bars_since_macd_cross": bars_since_cross,
        "momentum.cross_direction": cross_direction,
        "momentum.macd_state": state,
    }


def _state(hist_t: float, hist_slope: float, atr14: float) -> str:
    if not (np.isfinite(hist_t) and np.isfinite(atr14) and atr14 > 0):
        return "UNAVAILABLE"
    if abs(hist_t) < _NEUTRAL_HIST_ATR_MULT * atr14:
        return "NEUTRAL"
    if not np.isfinite(hist_slope):
        return "UNKNOWN"
    if hist_t > 0:
        return "BULLISH_EXPANDING" if hist_slope > 0 else "BULLISH_FADING"
    return "BEARISH_EXPANDING" if hist_slope < 0 else "BEARISH_FADING"


def _unavailable(hist: pd.DataFrame) -> dict:
    known_at = hist.index[-1].isoformat() if len(hist) else None
    return {
        "momentum._feature_version": FEATURE_VERSION,
        "momentum._source_timeframe": "1d",
        "momentum._known_at": known_at,
        "momentum._availability": False,
        "momentum.macd_line": None,
        "momentum.macd_signal": None,
        "momentum.macd_hist": None,
        "momentum.macd_line_slope": None,
        "momentum.macd_signal_slope": None,
        "momentum.macd_hist_slope": None,
        "momentum.macd_hist_acceleration": None,
        "momentum.macd_above_zero": None,
        "momentum.macd_below_zero": None,
        "momentum.macd_above_signal": None,
        "momentum.bars_since_macd_cross": None,
        "momentum.cross_direction": "UNAVAILABLE",
        "momentum.macd_state": "UNAVAILABLE",
    }
