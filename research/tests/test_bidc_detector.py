"""Sanity tests for BREAKOUT_INSIDE_DAY_CONTINUATION on synthetic setups."""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.detectors.breakout_inside_day_continuation import (
    BreakoutInsideDayContinuation,
)


def _flat_then_breakout(pre_bars: int = 100, level: float = 100.0) -> pd.DataFrame:
    """Synthetic: pre_bars of flat action below level (with an isolated pivot at
    level within the last 60 bars — pivot_lookback window), then a break-through,
    an inside day, a continuation."""
    highs = np.full(pre_bars, 96.0)
    lows = np.full(pre_bars, 94.0)
    closes = np.full(pre_bars, 95.0)
    opens = np.full(pre_bars, 95.0)
    # Isolated pivot at index (pre_bars - 40): well inside the 60-bar
    # pivot_lookback window when we hit t ≈ pre_bars + 1.
    piv_idx = pre_bars - 40
    highs[piv_idx] = level + 0.2
    highs[piv_idx - 1] = 97.0; highs[piv_idx + 1] = 97.0

    bars = list(zip(opens, highs, lows, closes))
    # Breakout day
    bars.append((level - 0.3, level + 1.5, level - 0.8, level + 1.0))
    # Inside day
    bars.append((level + 0.4, level + 1.2, level + 0.0, level + 0.9))
    # Continuation day
    bars.append((level + 1.1, level + 3.0, level + 1.0, level + 2.8))

    df = pd.DataFrame(
        {"open": [b[0] for b in bars], "high": [b[1] for b in bars],
         "low":  [b[2] for b in bars], "close": [b[3] for b in bars],
         "volume": 1_000_000},
        index=pd.date_range("2023-01-01", periods=len(bars), freq="D"),
    )
    return df


def test_bidc_fires_and_records_level_provenance():
    df = _flat_then_breakout(pre_bars=100, level=100.0)
    det = BreakoutInsideDayContinuation()
    occs = det.scan("SYN", df)
    assert len(occs) >= 1, "detector failed to fire"
    target_t0 = df.index[-2]
    hit = [o for o in occs if o.t0 == target_t0]
    assert hit, f"no occurrence at expected t0={target_t0}"
    o = hit[0]

    # Core plan intact
    assert o.side == "long"
    assert o.entry_bar_offset == 1

    # v0.2 fields present and populated
    assert o.features.get("was_breakout_at_tm1") is True
    assert o.features.get("holding_above_at_t") is True
    # Level provenance is stored
    lt = o.features.get("level_type")
    assert lt in ("swing_pivot", "horizontal_resistance", "round_number",
                  "prior_day_high", "prior_week_high", "prior_month_high"), (
        f"unexpected level_type: {lt}")
    # Ancillary numeric fields exist (may be None on some paths)
    assert "breakout_age_bars" in o.features
    assert "distance_to_level_atr" in o.features
    assert "room_to_next_level_atr" in o.features
    assert "room_to_next_level_R" in o.features
    # Entry-gap classification is populated
    assert o.features.get("entry_gap_flag") in (
        "clean", "gap_through_stop", "gap_through_target", "above_but_reachable",
    )


def test_bidc_does_not_fire_without_inside_day():
    n = 100
    prices = np.linspace(100, 130, n)
    df = pd.DataFrame(
        {"open": prices, "high": prices + 1.5, "low": prices - 0.2, "close": prices + 0.7,
         "volume": 1_000_000},
        index=pd.date_range("2023-01-01", periods=n, freq="D"),
    )
    det = BreakoutInsideDayContinuation()
    occs = det.scan("SYN", df)
    assert len(occs) == 0
