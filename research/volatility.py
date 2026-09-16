"""Extended Bollinger + volatility semantic label (PREREGISTRATION.md § 7-8).

Fields (raw first, class-fields derived) — all in `compression_volatility.*`.
Correlation note: bb_middle == SMA(close, 20); bb_state == COMPRESSION is
correlated with squeeze_on and low atr_ratio_60. See "Correlated feature
families" section of PREREGISTRATION.md.

UNAVAILABLE below 60 bars (20-period BB + 60-bar percentile window).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import math_utils as mu
from . import squeeze as sq


FEATURE_VERSION = "v0.3.0"

_MIN_BARS = 60
_BB_PERIOD = 20
_BB_NUM_STD = 2.0
_PCT_LOOKBACK = 60

# Preregistered BB state thresholds
_BB_COMPRESSION_PCT = 0.20
_BB_EXPANSION_PCT = 0.80

# Preregistered BB slope thresholds (fractional, normalized)
_BB_EXPANDING_SLOPE = 0.05
_BB_CONTRACTING_SLOPE = -0.05

# Volatility label thresholds
_DEEP_BB_PCT = 0.10
_DEEP_ATR_RATIO = 0.75
_COMP_ATR_RATIO = 0.85
_EXPANDING_BB_PCT = 0.60
_HIGH_VOL_ATR_RATIO = 1.5


def _num(x: float) -> float | None:
    return float(x) if np.isfinite(x) else None


def context_at(df: pd.DataFrame, t: int) -> dict:
    if t < 0 or t >= len(df):
        raise IndexError(f"t={t} out of range for df of length {len(df)}")
    hist = df.iloc[: t + 1]

    if len(hist) < _MIN_BARS:
        return _bb_unavailable(hist) | _label_unavailable(hist)

    close = hist["close"]
    price_t = float(close.iloc[-1])

    mean = close.rolling(_BB_PERIOD).mean()
    std = close.rolling(_BB_PERIOD).std()
    bb_upper = mean + _BB_NUM_STD * std
    bb_lower = mean - _BB_NUM_STD * std
    width = mu.bollinger_width(close, _BB_PERIOD, _BB_NUM_STD)
    pct = mu.bb_width_percentile(close, _BB_PERIOD, _PCT_LOOKBACK)

    mid_t = float(mean.iloc[-1]) if pd.notna(mean.iloc[-1]) else float("nan")
    up_t = float(bb_upper.iloc[-1]) if pd.notna(bb_upper.iloc[-1]) else float("nan")
    lo_t = float(bb_lower.iloc[-1]) if pd.notna(bb_lower.iloc[-1]) else float("nan")
    w_t = float(width.iloc[-1]) if pd.notna(width.iloc[-1]) else float("nan")
    pct_t = float(pct.iloc[-1]) if pd.notna(pct.iloc[-1]) else float("nan")

    if not all(np.isfinite(x) for x in [mid_t, up_t, lo_t, w_t, pct_t]):
        return _bb_unavailable(hist) | _label_unavailable(hist)

    # %B
    band_range = up_t - lo_t
    percent_b = (price_t - lo_t) / band_range if band_range > 0 else float("nan")

    # Midline / width slopes over 3 bars, normalized
    def _norm_slope(series: pd.Series) -> float:
        if len(series) < 4:
            return float("nan")
        cur = series.iloc[-1]
        past = series.iloc[-4]
        if not (pd.notna(cur) and pd.notna(past)) or past == 0:
            return float("nan")
        return float((cur - past) / 3.0 / abs(past))

    mid_slope = _norm_slope(mean)
    width_slope = _norm_slope(width)

    bb_expanding = bool(np.isfinite(width_slope) and width_slope > _BB_EXPANDING_SLOPE)
    bb_contracting = bool(np.isfinite(width_slope) and width_slope < _BB_CONTRACTING_SLOPE)

    if pct_t <= _BB_COMPRESSION_PCT:
        bb_state = "COMPRESSION"
    elif pct_t >= _BB_EXPANSION_PCT:
        bb_state = "EXPANSION"
    else:
        bb_state = "NORMAL"

    # ATR ratio (60d) — reuse math_utils helper
    ar_series = mu.atr_ratio(hist, 14, _PCT_LOOKBACK)
    atr_ratio_60 = float(ar_series.iloc[-1]) if pd.notna(ar_series.iloc[-1]) else float("nan")

    bb_block = {
        "compression_volatility._feature_version": FEATURE_VERSION,
        "compression_volatility._source_timeframe": "1d",
        "compression_volatility._known_at": hist.index[-1].isoformat(),
        "compression_volatility._bb_availability": True,
        "compression_volatility.bb_upper": _num(up_t),
        "compression_volatility.bb_middle": _num(mid_t),
        "compression_volatility.bb_lower": _num(lo_t),
        "compression_volatility.bb_width": _num(w_t),
        "compression_volatility.bb_width_percentile": _num(pct_t),
        "compression_volatility.bb_percent_b": _num(percent_b),
        "compression_volatility.bb_midline_slope": _num(mid_slope),
        "compression_volatility.bb_width_slope": _num(width_slope),
        "compression_volatility.bb_expanding": bb_expanding,
        "compression_volatility.bb_contracting": bb_contracting,
        "compression_volatility.price_above_midline": bool(price_t > mid_t),
        "compression_volatility.price_below_midline": bool(price_t < mid_t),
        "compression_volatility.touching_upper_band": bool(price_t >= 0.98 * up_t),
        "compression_volatility.touching_lower_band": bool(price_t <= 1.02 * lo_t),
        "compression_volatility.bb_state": bb_state,
        "compression_volatility.atr_ratio_60": _num(atr_ratio_60),
    }

    # Fold in squeeze block so downstream can reference it directly.
    squeeze_block = sq.context_at(df, t)
    for k, v in squeeze_block.items():
        if k in bb_block:
            continue  # keep BB values as authoritative when keys collide (metadata)
        bb_block[k] = v

    # Composite volatility label — precedence order per preregistration.
    squeeze_on = squeeze_block.get("compression_volatility.squeeze_on")
    label = _volatility_label(
        pct_t, atr_ratio_60, squeeze_on if isinstance(squeeze_on, bool) else None,
        bb_expanding,
    )
    bb_block["compression_volatility.volatility_label"] = label
    bb_block["compression_volatility.volatility_label_availability"] = label != "UNAVAILABLE"

    return bb_block


def _volatility_label(bb_pct: float, atr_ratio: float,
                      squeeze_on: bool | None, bb_expanding: bool) -> str:
    if not np.isfinite(bb_pct) or not np.isfinite(atr_ratio) or squeeze_on is None:
        return "UNAVAILABLE"
    # Precedence: DEEP_COMPRESSION > HIGH_VOLATILITY > EXPANDING > COMPRESSION > NORMAL.
    if bb_pct <= _DEEP_BB_PCT and atr_ratio < _DEEP_ATR_RATIO and squeeze_on:
        return "DEEP_COMPRESSION"
    if atr_ratio >= _HIGH_VOL_ATR_RATIO:
        return "HIGH_VOLATILITY"
    if bb_expanding and bb_pct >= _EXPANDING_BB_PCT:
        return "EXPANDING"
    if bb_pct <= _BB_COMPRESSION_PCT or atr_ratio < _COMP_ATR_RATIO or squeeze_on:
        return "COMPRESSION"
    return "NORMAL"


def _bb_unavailable(hist: pd.DataFrame) -> dict:
    known_at = hist.index[-1].isoformat() if len(hist) else None
    return {
        "compression_volatility._feature_version": FEATURE_VERSION,
        "compression_volatility._source_timeframe": "1d",
        "compression_volatility._known_at": known_at,
        "compression_volatility._bb_availability": False,
        "compression_volatility.bb_upper": None,
        "compression_volatility.bb_middle": None,
        "compression_volatility.bb_lower": None,
        "compression_volatility.bb_width": None,
        "compression_volatility.bb_width_percentile": None,
        "compression_volatility.bb_percent_b": None,
        "compression_volatility.bb_midline_slope": None,
        "compression_volatility.bb_width_slope": None,
        "compression_volatility.bb_expanding": None,
        "compression_volatility.bb_contracting": None,
        "compression_volatility.price_above_midline": None,
        "compression_volatility.price_below_midline": None,
        "compression_volatility.touching_upper_band": None,
        "compression_volatility.touching_lower_band": None,
        "compression_volatility.bb_state": "UNAVAILABLE",
        "compression_volatility.atr_ratio_60": None,
    }


def _label_unavailable(hist: pd.DataFrame) -> dict:
    return {
        "compression_volatility.volatility_label": "UNAVAILABLE",
        "compression_volatility.volatility_label_availability": False,
    }
