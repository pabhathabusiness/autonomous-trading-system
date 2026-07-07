"""
Heuristic chart-pattern detection on daily bars.

IMPORTANT: these are approximations. Real pattern recognition is
subjective and these rule-based detectors will produce false positives
and miss valid formations. They are treated as *one edge among many* in
the confidence stack -- never a standalone trade trigger. Each detector
returns (detected: bool, detail: str).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _linfit(y: np.ndarray) -> tuple[float, float]:
    """Return (slope, r2) of a least-squares line through y."""
    x = np.arange(len(y))
    if len(y) < 2:
        return 0.0, 0.0
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return float(slope), float(r2)


def _pole_then_base(df: pd.DataFrame, pole_bars: int, base_bars: int) -> tuple[bool, float, pd.DataFrame]:
    """Detect a sharp up-move (pole) immediately followed by a
    consolidation (base). Returns (has_pole, pole_gain_pct, base_df)."""
    if len(df) < pole_bars + base_bars:
        return False, 0.0, df.iloc[0:0]
    base = df.iloc[-base_bars:]
    pole = df.iloc[-(pole_bars + base_bars):-base_bars]
    if pole.empty:
        return False, 0.0, base
    pole_gain = (pole["Close"].iloc[-1] - pole["Close"].iloc[0]) / pole["Close"].iloc[0] * 100
    return pole_gain >= 12, float(pole_gain), base


def detect_bull_flag(df: pd.DataFrame) -> tuple[bool, str]:
    """Strong pole up, then a shallow downward/sideways channel on
    contracting range near the highs."""
    has_pole, gain, base = _pole_then_base(df, pole_bars=10, base_bars=8)
    if not has_pole or base.empty:
        return False, ""
    slope, _ = _linfit(base["Close"].values)
    base_range = (base["High"].max() - base["Low"].min()) / base["Close"].mean() * 100
    # flag: mild pullback/drift (slope <= 0 but not a collapse) and tight range
    if slope <= 0 and base_range <= max(8.0, gain * 0.5):
        return True, f"bull flag (pole +{gain:.0f}%, tight base)"
    return False, ""


def detect_pennant(df: pd.DataFrame) -> tuple[bool, str]:
    """Pole up, then converging highs and lows (symmetrical contraction)."""
    has_pole, gain, base = _pole_then_base(df, pole_bars=10, base_bars=10)
    if not has_pole or len(base) < 6:
        return False, ""
    high_slope, _ = _linfit(base["High"].values)
    low_slope, _ = _linfit(base["Low"].values)
    if high_slope < 0 and low_slope > 0:  # converging
        return True, f"pennant (pole +{gain:.0f}%, converging)"
    return False, ""


def detect_ascending_triangle(df: pd.DataFrame, bars: int = 30) -> tuple[bool, str]:
    """Flat (horizontal) resistance + rising support -> bullish."""
    if len(df) < bars:
        return False, ""
    window = df.iloc[-bars:]
    high_slope, high_r2 = _linfit(window["High"].values)
    low_slope, _ = _linfit(window["Low"].values)
    avg = window["Close"].mean()
    flat_top = abs(high_slope) / avg * 100 < 0.15  # nearly horizontal highs
    rising_bottom = low_slope / avg * 100 > 0.10
    if flat_top and rising_bottom:
        return True, "ascending triangle (flat resistance, rising lows)"
    return False, ""


def detect_descending_triangle_break(df: pd.DataFrame, bars: int = 30) -> tuple[bool, str]:
    """Descending triangle = flat support + falling highs (normally
    bearish). We only fire when price has *broken back up* through the
    falling-highs trendline, i.e. a failed-breakdown reversal long."""
    if len(df) < bars:
        return False, ""
    window = df.iloc[-bars:]
    high_slope, _ = _linfit(window["High"].values)
    low_slope, _ = _linfit(window["Low"].values)
    avg = window["Close"].mean()
    falling_top = high_slope / avg * 100 < -0.10
    flat_bottom = abs(low_slope) / avg * 100 < 0.15
    if falling_top and flat_bottom:
        # descending triangle present; is the last close breaking above the
        # projected upper trendline (bullish break of a bearish pattern)?
        x = np.arange(len(window))
        upper = np.polyval(np.polyfit(x, window["High"].values, 1), x[-1])
        if window["Close"].iloc[-1] > upper:
            return True, "descending-triangle upside break (reversal)"
    return False, ""


def detect_all(df: pd.DataFrame) -> dict[str, str]:
    """Run every bullish detector; return {pattern_name: detail} for hits."""
    detectors = {
        "bull_flag": detect_bull_flag,
        "pennant": detect_pennant,
        "ascending_triangle": detect_ascending_triangle,
        "descending_triangle_break": detect_descending_triangle_break,
    }
    hits: dict[str, str] = {}
    for name, fn in detectors.items():
        try:
            ok, detail = fn(df)
            if ok:
                hits[name] = detail
        except Exception:
            continue
    return hits
