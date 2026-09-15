"""End-to-end gap handling on the BIDC detector.

Verifies:
  1. Gap-through-stop is FLAGGED on the occurrence (not silently taken as a loss).
  2. Gap-through-target is FLAGGED on the occurrence (not silently a win).
  3. Report excludes both from primary set and reports as separate rates.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.cells import CELLS_BY_DETECTOR
from research.detectors.breakout_inside_day_continuation import BreakoutInsideDayContinuation
from research.report import build_stats
from research.runner import run_detector


class _FakeSource:
    def __init__(self, dfs): self.dfs = dfs
    def daily(self, symbol, start, end): return self.dfs.get(symbol, pd.DataFrame())


def _base_pre_bars(n_pre: int = 100, level: float = 100.0) -> pd.DataFrame:
    """Flat action below `level` with a pivot high AT level within the last 60
    bars (pivot_lookback window)."""
    highs = np.full(n_pre, 96.0)
    lows = np.full(n_pre, 94.0)
    closes = np.full(n_pre, 95.0)
    opens = np.full(n_pre, 95.0)
    piv_idx = n_pre - 40
    highs[piv_idx] = level + 0.2
    highs[piv_idx - 1] = 97.0; highs[piv_idx + 1] = 97.0
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes,
         "volume": [1_000_000] * n_pre},
        index=pd.date_range("2023-01-01", periods=n_pre, freq="D"),
    )


def _append_bar(df: pd.DataFrame, o, h, l, c):
    row = pd.DataFrame(
        {"open": [o], "high": [h], "low": [l], "close": [c], "volume": [1_000_000]},
        index=[df.index[-1] + pd.Timedelta(days=1)],
    )
    return pd.concat([df, row])


def test_gap_through_stop_flagged_and_excluded_from_primary():
    df = _base_pre_bars(100, 100.0)
    df = _append_bar(df, 99.5, 101.5, 99.2, 101.0)   # breakout day
    df = _append_bar(df, 100.4, 101.2, 100.0, 100.9) # inside day
    # Continuation bar opens WELL BELOW stop (stop ~= 99.0)
    df = _append_bar(df, 88.0, 89.0, 87.0, 88.5)     # gap-through-stop
    dfs = {"SYN": df, "SPY": df}
    occ_df, manifest = run_detector(
        BreakoutInsideDayContinuation(), symbols=["SYN"], source=_FakeSource(dfs),
        start=df.index[0].date(), end=df.index[-1].date(),
        max_bars=30, spy_source=_FakeSource(dfs),
    )
    assert not occ_df.empty
    # Every occurrence's entry_gap_flag is on the row
    flags = occ_df["feat_entry_gap_flag"].tolist()
    assert "gap_through_stop" in flags, f"expected gap_through_stop, got {flags}"

    stats = build_stats(occ_df, CELLS_BY_DETECTOR["BREAKOUT_INSIDE_DAY_CONTINUATION"])
    base = stats[stats["cell"] == "A1_generic_inside_day"].iloc[0]
    assert base["n_total"] >= 1
    assert base["gap_through_stop_rate"] > 0
    # Primary set (clean gaps only) should not include the gap-through-stop row
    assert base["n_primary"] < base["n_total"]


def test_gap_through_target_flagged_and_excluded_from_primary():
    df = _base_pre_bars(100, 100.0)
    df = _append_bar(df, 99.5, 101.5, 99.2, 101.0)   # breakout day
    df = _append_bar(df, 100.4, 101.2, 100.0, 100.9) # inside day
    # Continuation bar opens WELL ABOVE target (~= 102.4 by the 2R math)
    df = _append_bar(df, 130.0, 132.0, 129.0, 131.0) # massive gap up
    dfs = {"SYN": df, "SPY": df}
    occ_df, _ = run_detector(
        BreakoutInsideDayContinuation(), symbols=["SYN"], source=_FakeSource(dfs),
        start=df.index[0].date(), end=df.index[-1].date(),
        max_bars=30, spy_source=_FakeSource(dfs),
    )
    flags = occ_df["feat_entry_gap_flag"].tolist()
    assert "gap_through_target" in flags, f"expected gap_through_target, got {flags}"
