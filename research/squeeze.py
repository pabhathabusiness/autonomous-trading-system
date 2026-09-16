"""TTM Squeeze — exact preregistered math (PREREGISTRATION.md § 6).

- Bollinger Bands: SMA(close, 20) ± 2·stddev(close, 20).
- Keltner Channels: EMA(close, 20) ± 1.5·ATR(20). Note the ATR period
  here is **20**, not the 14 used elsewhere in this repo.
- squeeze_on at bar t iff BB_upper < KC_upper AND BB_lower > KC_lower.
- TTM momentum: linear-regression fit at bar t of the series
    close_i − ((donchian_high_20 + donchian_low_20) / 2 + SMA(close, 20)) / 2
  over the last 20 bars. Reported value is the fitted value at the last
  bar (equivalent to the classic "TTM histogram" bar).

UNAVAILABLE below 40 bars (20 for BB/KC + 20 for the linear-regression
window). Correlation note: outputs here belong to the volatility-
compression family and are correlated with `bb_width_percentile`,
`atr_ratio`, and any BB-state-based label.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import math_utils as mu


FEATURE_VERSION = "v0.3.0"

_MIN_BARS = 40
_BB_PERIOD = 20
_BB_NUM_STD = 2.0
_KC_PERIOD = 20
_KC_ATR_MULT = 1.5
_TTM_WINDOW = 20


def _num(x: float) -> float | None:
    return float(x) if np.isfinite(x) else None


def _linreg_last_fit(y: np.ndarray) -> float:
    """Return the linear-regression fitted value at the last index of `y`.
    x = 0..n-1. If y contains any NaN or len < 2, returns NaN."""
    if len(y) < 2 or np.any(~np.isfinite(y)):
        return float("nan")
    x = np.arange(len(y), dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    return float(slope * (len(y) - 1) + intercept)


def context_at(df: pd.DataFrame, t: int) -> dict:
    if t < 0 or t >= len(df):
        raise IndexError(f"t={t} out of range for df of length {len(df)}")
    hist = df.iloc[: t + 1]

    if len(hist) < _MIN_BARS:
        return _unavailable(hist)

    close = hist["close"]

    bb_mean = close.rolling(_BB_PERIOD).mean()
    bb_std = close.rolling(_BB_PERIOD).std()
    bb_upper = bb_mean + _BB_NUM_STD * bb_std
    bb_lower = bb_mean - _BB_NUM_STD * bb_std

    kc_mid = close.ewm(span=_KC_PERIOD, adjust=False).mean()
    kc_atr = mu.atr(hist, _KC_PERIOD)
    kc_upper = kc_mid + _KC_ATR_MULT * kc_atr
    kc_lower = kc_mid - _KC_ATR_MULT * kc_atr

    def _on_row(i: int) -> bool | float:
        if (i < _BB_PERIOD or i < _KC_PERIOD or
                pd.isna(bb_upper.iloc[i]) or pd.isna(kc_upper.iloc[i]) or
                pd.isna(bb_lower.iloc[i]) or pd.isna(kc_lower.iloc[i])):
            return float("nan")
        return bool(bb_upper.iloc[i] < kc_upper.iloc[i] and bb_lower.iloc[i] > kc_lower.iloc[i])

    on_t = _on_row(len(hist) - 1)
    if not isinstance(on_t, bool):
        return _unavailable(hist)

    # Contiguous squeeze_on run ending at t
    duration = 0
    for i in range(len(hist) - 1, -1, -1):
        v = _on_row(i)
        if v is True:
            duration += 1
        else:
            break

    # Bars since last off→on-to-off release
    on_series = pd.Series([_on_row(i) for i in range(len(hist))], index=hist.index)
    # Coerce non-bool (NaN) to np.nan for masking
    ob = on_series.map(lambda v: v if isinstance(v, bool) else np.nan)
    release_bars, first_release_bar = _find_last_release(ob)

    # TTM momentum value at t
    donchian_hi_20 = hist["high"].rolling(_TTM_WINDOW).max()
    donchian_lo_20 = hist["low"].rolling(_TTM_WINDOW).min()
    sma_20 = close.rolling(_TTM_WINDOW).mean()
    series_for_fit = close - ((donchian_hi_20 + donchian_lo_20) / 2.0 + sma_20) / 2.0
    tail = series_for_fit.tail(_TTM_WINDOW).to_numpy()
    momentum = _linreg_last_fit(tail)

    # Momentum slope + acceleration (3-bar finite diffs of momentum values)
    mom_series = pd.Series(
        [_linreg_last_fit(series_for_fit.iloc[i - _TTM_WINDOW + 1: i + 1].to_numpy())
         if i >= _TTM_WINDOW - 1 else float("nan")
         for i in range(len(hist))],
        index=hist.index,
    )
    if len(mom_series) >= 4 and pd.notna(mom_series.iloc[-4]):
        mom_slope = float((mom_series.iloc[-1] - mom_series.iloc[-4]) / 3.0)
    else:
        mom_slope = float("nan")
    if len(mom_series) >= 7 and pd.notna(mom_series.iloc[-4]) and pd.notna(mom_series.iloc[-7]):
        past_slope = float((mom_series.iloc[-4] - mom_series.iloc[-7]) / 3.0)
        mom_accel = mom_slope - past_slope
    else:
        mom_accel = float("nan")

    release_direction = "none"
    if first_release_bar is not None:
        try:
            b_iloc = hist.index.get_loc(first_release_bar)
            val = mom_series.iloc[b_iloc] if b_iloc < len(mom_series) else float("nan")
            if pd.notna(val):
                release_direction = "up" if val > 0 else ("down" if val < 0 else "none")
        except KeyError:
            pass

    return {
        "compression_volatility._feature_version": FEATURE_VERSION,
        "compression_volatility._source_timeframe": "1d",
        "compression_volatility._known_at": hist.index[-1].isoformat(),
        "compression_volatility._squeeze_availability": True,
        "compression_volatility.squeeze_on": bool(on_t),
        "compression_volatility.squeeze_off": bool(not on_t),
        "compression_volatility.squeeze_duration_bars": int(duration),
        "compression_volatility.bars_since_squeeze_release": release_bars,
        "compression_volatility.first_release_bar": first_release_bar.isoformat() if first_release_bar is not None else None,
        "compression_volatility.squeeze_release_direction": release_direction,
        "compression_volatility.ttm_momentum_value": _num(momentum),
        "compression_volatility.ttm_momentum_slope": _num(mom_slope),
        "compression_volatility.ttm_momentum_acceleration": _num(mom_accel),
        "compression_volatility.ttm_momentum_positive": bool(np.isfinite(momentum) and momentum > 0),
        "compression_volatility.ttm_momentum_negative": bool(np.isfinite(momentum) and momentum < 0),
    }


def _find_last_release(on_series: pd.Series) -> tuple[int | None, pd.Timestamp | None]:
    """Find the most recent OFF-to-ON-then-OFF transition ("release") ending
    within the trailing 250 bars.

    We define a "release" as bar j such that on_series[j-1] is True and
    on_series[j] is False. Returns (bars_since_j, index_of_j), or (None, None).
    """
    tail = on_series.tail(250)
    releases = []
    prev = None
    for i, v in enumerate(tail.to_numpy()):
        if isinstance(prev, bool) and prev is True and (v is False or v == 0.0):
            releases.append(i)
        prev = v if isinstance(v, bool) else prev
    if not releases:
        return None, None
    j = releases[-1]
    return int(len(tail) - 1 - j), tail.index[j]


def _unavailable(hist: pd.DataFrame) -> dict:
    known_at = hist.index[-1].isoformat() if len(hist) else None
    return {
        "compression_volatility._feature_version": FEATURE_VERSION,
        "compression_volatility._source_timeframe": "1d",
        "compression_volatility._known_at": known_at,
        "compression_volatility._squeeze_availability": False,
        "compression_volatility.squeeze_on": None,
        "compression_volatility.squeeze_off": None,
        "compression_volatility.squeeze_duration_bars": None,
        "compression_volatility.bars_since_squeeze_release": None,
        "compression_volatility.first_release_bar": None,
        "compression_volatility.squeeze_release_direction": "UNAVAILABLE",
        "compression_volatility.ttm_momentum_value": None,
        "compression_volatility.ttm_momentum_slope": None,
        "compression_volatility.ttm_momentum_acceleration": None,
        "compression_volatility.ttm_momentum_positive": None,
        "compression_volatility.ttm_momentum_negative": None,
    }
