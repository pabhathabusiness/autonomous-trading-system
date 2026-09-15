"""Enforce that features frozen at bar t depend ONLY on bars ≤ t.

Method: build a full history, freeze features at bar t, then MUTATE all bars
after t to obviously extreme garbage values, re-freeze features at t. If any
feature changes, the extractor is peeking forward — fail.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research import features as feat_mod


def _random_ohlc(n: int = 200, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    prices = 100 * (1 + rng.normal(0, 0.01, size=n)).cumprod()
    highs = prices * (1 + np.abs(rng.normal(0, 0.005, size=n)))
    lows = prices * (1 - np.abs(rng.normal(0, 0.005, size=n)))
    opens = prices * (1 + rng.normal(0, 0.002, size=n))
    volumes = rng.integers(500_000, 5_000_000, size=n)
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": prices, "volume": volumes},
        index=pd.date_range("2023-01-01", periods=n, freq="D"),
    )


def _corrupt_future(df: pd.DataFrame, t: int) -> pd.DataFrame:
    corrupted = df.copy()
    if t + 1 < len(df):
        corrupted.iloc[t + 1:, corrupted.columns.get_loc("open")] = -9999.0
        corrupted.iloc[t + 1:, corrupted.columns.get_loc("high")] = -9999.0
        corrupted.iloc[t + 1:, corrupted.columns.get_loc("low")] = -9999.0
        corrupted.iloc[t + 1:, corrupted.columns.get_loc("close")] = -9999.0
        corrupted.iloc[t + 1:, corrupted.columns.get_loc("volume")] = 0
    return corrupted


@pytest.mark.parametrize("t", [80, 120, 150, 180])
def test_features_do_not_change_when_future_is_corrupted(t: int):
    df = _random_ohlc(n=200)
    original = feat_mod.freeze_at(df, t)
    corrupted = feat_mod.freeze_at(_corrupt_future(df, t), t)
    for k, v in original.items():
        cv = corrupted[k]
        if v is None and cv is None:
            continue
        if isinstance(v, float) and np.isnan(v):
            assert isinstance(cv, float) and np.isnan(cv), f"{k} changed from NaN to {cv!r}"
        else:
            assert v == cv, f"lookahead detected in feature {k!r}: {v!r} vs {cv!r}"


def test_detector_scan_result_does_not_change_with_future_corruption():
    """Detector-level test: same occurrences at t should be produced whether or
    not bars after t exist. Only checks features on the last non-entry-bar
    Occurrence to avoid needing the +1 open."""
    from research.detectors.breakout_inside_day_continuation import (
        BreakoutInsideDayContinuation,
    )

    df = _random_ohlc(n=200)
    det = BreakoutInsideDayContinuation()
    full = det.scan("TEST", df)
    if not full:
        # Random data may not produce a hit; that's fine — the point is that
        # any produced occurrence in a truncated series matches its own frozen
        # feature dict from the full series.
        return
    # Take an early occurrence and truncate df to just past its entry bar
    occ = full[0]
    t0_iloc = df.index.get_loc(occ.t0)
    truncated = df.iloc[: t0_iloc + 2]  # keep entry bar at t0+1
    early = BreakoutInsideDayContinuation().scan("TEST", truncated)
    assert early, "detector produced no occurrences on truncated history that had at least one"
    ea = early[0]
    for k in ("was_breakout_at_tm1", "holding_above_at_t", "compression",
              "ema_stack_up", "macd_state", "fresh_macd_reaccel_up"):
        assert occ.features.get(k) == ea.features.get(k), (
            f"feature {k!r} changed with future truncation: {occ.features.get(k)!r} vs {ea.features.get(k)!r}"
        )
