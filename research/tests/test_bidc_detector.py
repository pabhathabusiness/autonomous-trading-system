"""Sanity tests for BREAKOUT_INSIDE_DAY_CONTINUATION on synthetic setups.

Not backtest-quality — just verifies the detector fires when expected and
doesn't fire on obvious non-setups.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.detectors.breakout_inside_day_continuation import (
    BreakoutInsideDayContinuation,
)


def _flat_then_breakout(pre_bars: int = 80, level: float = 100.0) -> pd.DataFrame:
    """Build a synthetic history:
      - pre_bars of near-flat action below `level` (creating a pivot high at level)
      - a break-through-and-close-above bar
      - an inside day
      - a small continuation bar
    """
    rng = np.random.default_rng(1)
    # Flat around level - 2, occasional pivot at exactly `level`
    body = 95 + rng.normal(0, 0.3, pre_bars).cumsum() * 0.0
    highs = body + 1.5
    lows = body - 1.5
    closes = body
    opens = body

    # Insert a pivot high at level around index 20 (surrounded by lower bars)
    piv_idx = 20
    highs[piv_idx] = level + 0.2   # actual pivot
    highs[piv_idx - 3: piv_idx] = np.linspace(96, 98, 3)
    highs[piv_idx + 1: piv_idx + 4] = np.linspace(98, 96, 3)
    # after that, prices drift a bit but don't cross level again for the required window
    highs[piv_idx + 4: pre_bars] = 95 + rng.normal(0, 0.2, pre_bars - piv_idx - 4).cumsum() * 0
    for i in range(pre_bars):
        lows[i] = min(lows[i], highs[i] - 0.5)
        closes[i] = min(closes[i], highs[i])

    # Now three added bars: breakout, inside, continuation
    bars = list(zip(opens, highs, lows, closes))
    # Breakout day: close above level
    bars.append((level - 0.3, level + 1.5, level - 0.8, level + 1.0))
    # Inside day: fully contained inside breakout day
    bars.append((level + 0.4, level + 1.2, level + 0.0, level + 0.9))
    # Continuation day: opens above the inside close (so entry has a shot)
    bars.append((level + 1.1, level + 3.0, level + 1.0, level + 2.8))

    df = pd.DataFrame(
        {"open": [b[0] for b in bars], "high": [b[1] for b in bars],
         "low":  [b[2] for b in bars], "close": [b[3] for b in bars],
         "volume": 1_000_000},
        index=pd.date_range("2023-01-01", periods=len(bars), freq="D"),
    )
    return df


def test_bidc_fires_on_synthetic_setup():
    df = _flat_then_breakout(pre_bars=80, level=100.0)
    det = BreakoutInsideDayContinuation()
    occs = det.scan("SYN", df)
    # We expect at least one occurrence at the synthetic inside day
    assert len(occs) >= 1, "detector failed to fire on obvious inside-day-after-breakout"
    # Locate the one at t = len(df) - 2 (the inside day)
    target_t0 = df.index[-2]
    hit = [o for o in occs if o.t0 == target_t0]
    assert hit, f"no occurrence at expected t0={target_t0}"
    o = hit[0]
    assert o.side == "long"
    assert o.entry_bar_offset == 1
    # was_breakout should be True since bar t-1 crossed the untouched level
    assert o.features.get("was_breakout_at_tm1") is True
    # holding_above should be True (close of inside day above level)
    assert o.features.get("holding_above_at_t") is True


def test_bidc_does_not_fire_without_inside_day():
    # Straight uptrending series with no inside days
    n = 100
    prices = np.linspace(100, 130, n)
    df = pd.DataFrame(
        {"open": prices, "high": prices + 1.5, "low": prices - 0.2, "close": prices + 0.7,
         "volume": 1_000_000},
        index=pd.date_range("2023-01-01", periods=n, freq="D"),
    )
    det = BreakoutInsideDayContinuation()
    occs = det.scan("SYN", df)
    assert len(occs) == 0, "detector fired on obviously-not-inside-day series"
