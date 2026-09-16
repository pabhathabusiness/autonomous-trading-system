"""Resolver unit tests. WIN / LOSS / AMBIGUOUS / TIMEOUT (v0.2)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from research.resolve import Resolution, resolve, classify_entry_gap


def _bar(o, h, l, c, v=1_000_000):
    return {"open": o, "high": h, "low": l, "close": c, "volume": v}


def _df(bars):
    return pd.DataFrame(bars, index=pd.date_range("2024-01-01", periods=len(bars), freq="D"))


# ------------------------------------------------------------------ core outcomes
def test_long_win():
    df = _df([_bar(100, 111, 99, 108), _bar(108, 112, 106, 110)])
    r = resolve(100, 95, 110, "long", df, max_bars=10)
    assert r.outcome == "win"
    assert r.r_multiple == 2.0
    assert r.r_multiple_conservative == 2.0
    assert r.r_multiple_optimistic == 2.0
    assert r.bars_to_resolve == 1


def test_long_loss():
    df = _df([_bar(100, 102, 94, 96)])
    r = resolve(100, 95, 110, "long", df, max_bars=10)
    assert r.outcome == "loss"
    assert r.r_multiple == -1.0


def test_ambiguous_is_first_class_not_loss():
    # Bar spans both stop (95) and target (110). NO longer coerced to loss.
    df = _df([_bar(100, 112, 94, 100)])
    r = resolve(100, 95, 110, "long", df, max_bars=10)
    assert r.outcome == "ambiguous"
    assert math.isnan(r.r_multiple)
    assert r.r_multiple_conservative == -1.0
    assert r.r_multiple_optimistic == 2.0
    assert r.bars_to_resolve == 1


def test_timeout_r_multiple_from_last_close():
    df = _df([_bar(100, 102, 99, 101), _bar(101, 103, 100, 102), _bar(102, 103, 101, 102)])
    r = resolve(100, 95, 110, "long", df, max_bars=3)
    assert r.outcome == "timeout"
    # Last close = 102 → (102-100)/5 = 0.4R
    assert abs(r.r_multiple - 0.4) < 1e-9
    assert r.r_multiple_conservative == r.r_multiple  # timeout: no ambig branch
    assert r.r_multiple_optimistic == r.r_multiple


def test_short_win_and_loss():
    df = _df([_bar(100, 101, 89, 92)])
    assert resolve(100, 105, 90, "short", df).outcome == "win"
    df = _df([_bar(100, 106, 99, 105)])
    assert resolve(100, 105, 90, "short", df).outcome == "loss"


def test_short_ambiguous():
    # Short entry 100, stop 105, target 90. Bar spans BOTH.
    df = _df([_bar(100, 106, 89, 95)])
    r = resolve(100, 105, 90, "short", df)
    assert r.outcome == "ambiguous"


def test_mae_mfe_recorded_across_walk():
    df = _df([_bar(100, 108, 96, 100), _bar(100, 111, 100, 110)])
    r = resolve(100, 95, 110, "long", df, max_bars=10)
    assert r.outcome == "win"
    assert 0.75 <= r.mae <= 0.85     # bar 1 dip to 96 → 0.8R adverse
    assert r.mfe >= 1.55             # walk sees ≥ 1.6R favorable


def test_entry_equals_stop_raises():
    df = _df([_bar(100, 101, 99, 100)])
    try:
        resolve(100, 100, 110, "long", df)
    except ValueError:
        return
    assert False, "expected ValueError for zero risk_unit"


# ------------------------------------------------------------------ entry gaps
def test_classify_entry_gap_clean_long():
    assert classify_entry_gap(entry_open=100, stop=95, target=110, side="long") == "clean"


def test_classify_entry_gap_through_stop_long():
    assert classify_entry_gap(entry_open=94, stop=95, target=110, side="long") == "gap_through_stop"


def test_classify_entry_gap_through_target_long():
    assert classify_entry_gap(entry_open=111, stop=95, target=110, side="long") == "gap_through_target"


def test_classify_entry_gap_short_symmetry():
    # For a short: stop is ABOVE entry, target is BELOW.
    assert classify_entry_gap(entry_open=100, stop=105, target=90, side="short") == "clean"
    assert classify_entry_gap(entry_open=106, stop=105, target=90, side="short") == "gap_through_stop"
    assert classify_entry_gap(entry_open=89, stop=105, target=90, side="short") == "gap_through_target"
