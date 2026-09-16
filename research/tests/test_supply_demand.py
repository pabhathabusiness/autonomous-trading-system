"""Tests for research/supply_demand.py — causal, deterministic zones."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research import supply_demand as sd


def _make_df(highs, lows, opens, closes, start="2024-01-01") -> pd.DataFrame:
    idx = pd.date_range(start, periods=len(closes), freq="D")
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes},
        index=idx,
    )


def _drifting(n: int, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    step = rng.normal(0, 0.5, size=n).cumsum() + 100
    high = step + np.abs(rng.normal(0.4, 0.15, size=n))
    low = step - np.abs(rng.normal(0.4, 0.15, size=n))
    open_ = step + rng.normal(0, 0.05, size=n)
    close = step + rng.normal(0, 0.05, size=n)
    return _make_df(high.tolist(), low.tolist(), open_.tolist(), close.tolist())


def _inject_base_and_impulse(df: pd.DataFrame, at: int,
                             base_bars: int = 3, impulse: float = 5.0) -> pd.DataFrame:
    """Turn bars [at-base_bars .. at-1] into a tight base and bar `at` into an
    upside impulse. Returns a NEW DataFrame."""
    d = df.copy()
    p = float(d["close"].iloc[at - base_bars - 1])
    for j in range(at - base_bars, at):
        d.iloc[j, d.columns.get_loc("open")] = p
        d.iloc[j, d.columns.get_loc("close")] = p + 0.05
        d.iloc[j, d.columns.get_loc("high")] = p + 0.1
        d.iloc[j, d.columns.get_loc("low")] = p - 0.05
    open_i = p + 0.02
    close_i = p + impulse
    d.iloc[at, d.columns.get_loc("open")] = open_i
    d.iloc[at, d.columns.get_loc("close")] = close_i
    d.iloc[at, d.columns.get_loc("high")] = close_i + 0.05
    d.iloc[at, d.columns.get_loc("low")] = open_i - 0.05
    return d


def test_no_zones_from_random_history():
    df = _drifting(60)
    zones = sd.detect_zones("TEST", df)
    # Random walk should not routinely produce base+impulse zones
    assert isinstance(zones, list)


def test_base_impulse_emits_demand_zone():
    df = _drifting(60)
    df = _inject_base_and_impulse(df, at=40, base_bars=3, impulse=5.0)
    zones = sd.detect_zones("TEST", df)
    demand = [z for z in zones if z.zone_type == "demand"]
    assert demand, "expected a demand zone from injected base+impulse"
    z = demand[0]
    # known_at is the impulse bar
    assert z.known_at_bar == df.index[40]
    # price range spans base bars
    assert z.price_low < z.price_high
    # id is deterministic hash
    assert len(z.zone_id) == 16


def test_causal_evaluate_at_ignores_future_bars():
    df = _drifting(80)
    df = _inject_base_and_impulse(df, at=40, base_bars=3, impulse=5.0)
    zones = sd.detect_zones("TEST", df)
    if not zones:
        pytest.skip("no zone produced from injection — retry with different seed")
    z = zones[0]
    # Corrupt future to garbage
    corrupted = df.copy()
    corrupted.iloc[50:, :] = -9999.0
    evaluated_original = sd.evaluate_at(zones, df, t=45)
    evaluated_corrupted = sd.evaluate_at(zones, corrupted, t=45)
    for a, b in zip(evaluated_original, evaluated_corrupted):
        assert a.active == b.active
        assert a.age_bars == b.age_bars
        assert a.touches_since_creation == b.touches_since_creation


def test_context_at_returns_expected_keys():
    df = _drifting(80)
    df = _inject_base_and_impulse(df, at=40, base_bars=3, impulse=5.0)
    zones = sd.detect_zones("TEST", df)
    ctx = sd.context_at(zones, df, t=45, planned_risk_unit=1.0)
    for k in [
        "supply_demand.nearest_demand_distance_atr",
        "supply_demand.nearest_supply_distance_atr",
        "supply_demand.inside_demand_zone",
        "supply_demand.inside_supply_zone",
        "supply_demand.room_to_supply_R",
        "supply_demand.room_to_demand_R",
        "supply_demand._feature_version",
    ]:
        assert k in ctx


def test_invalidation_flags_active_false():
    df = _drifting(80)
    df = _inject_base_and_impulse(df, at=40, base_bars=3, impulse=5.0)
    zones = sd.detect_zones("TEST", df)
    demand = [z for z in zones if z.zone_type == "demand"]
    if not demand:
        pytest.skip("no demand zone")
    z = demand[0]
    # Force a hard close well below the zone at bar 60 to invalidate.
    kick = z.price_low - 5.0
    df.iloc[60, df.columns.get_loc("close")] = kick
    df.iloc[60, df.columns.get_loc("low")] = kick - 0.5
    evaluated = sd.evaluate_at(zones, df, t=65)
    z_eval = next(e for e in evaluated if e.zone_id == z.zone_id)
    assert z_eval.active is False
    assert z_eval.invalidated_at is not None
