"""Per-bar SPY regime tag.

Mirrors src/market_analyzer.MarketAnalyzer's composite score, re-implemented
so research/ has zero coupling to production imports. Any drift is a bug to
reconcile in a follow-up.

Rules (locked):
  weights = {1d: 0.15, 5d: 0.30, 10d: 0.30, 30d: 0.25}
  composite = weighted sum of pct changes on SPY closes
  BULL if composite >= 2.0
  BEAR if composite <= -2.0
  else NEUTRAL
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


_WEIGHTS = {"1d": 0.15, "5d": 0.30, "10d": 0.30, "30d": 0.25}
_BULL_TH = 2.0
_BEAR_TH = -2.0


def _pct(closes: pd.Series, periods: int) -> pd.Series:
    return (closes / closes.shift(periods) - 1.0) * 100.0


def regime_series(spy_closes: pd.Series) -> pd.Series:
    """One tag per bar. Requires at least ~31 bars of SPY history for the first
    valid row; rows before that are 'UNKNOWN'."""
    p1 = _pct(spy_closes, 1)
    p5 = _pct(spy_closes, 5)
    p10 = _pct(spy_closes, 10)
    p30 = _pct(spy_closes, 30)
    composite = (
        _WEIGHTS["1d"] * p1
        + _WEIGHTS["5d"] * p5
        + _WEIGHTS["10d"] * p10
        + _WEIGHTS["30d"] * p30
    )
    tag = pd.Series("NEUTRAL", index=spy_closes.index)
    tag = tag.mask(composite >= _BULL_TH, "BULL")
    tag = tag.mask(composite <= _BEAR_TH, "BEAR")
    tag = tag.mask(composite.isna(), "UNKNOWN")
    return tag


def tag_at(spy_closes: pd.Series, timestamp: pd.Timestamp) -> str:
    """Regime at a given bar timestamp. If SPY doesn't have that exact
    timestamp (weekend, etc.), we use the most recent SPY close ≤ timestamp."""
    if len(spy_closes) == 0:
        return "UNKNOWN"
    idx = spy_closes.index.searchsorted(timestamp, side="right") - 1
    if idx < 0:
        return "UNKNOWN"
    tag = regime_series(spy_closes.iloc[: idx + 1])
    return tag.iloc[-1]
