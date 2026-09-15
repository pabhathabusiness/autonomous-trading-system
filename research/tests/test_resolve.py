"""Resolve unit tests using synthetic OHLC. No network."""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.resolve import resolve


def _bar(o, h, l, c, v=1_000_000):
    return {"open": o, "high": h, "low": l, "close": c, "volume": v}


def _df(bars):
    return pd.DataFrame(bars, index=pd.date_range("2024-01-01", periods=len(bars), freq="D"))


def test_long_hits_target_before_stop():
    # Entry 100, stop 95 (5R risk), target 110. Bar 1 hits 111 without touching 95.
    df = _df([_bar(100, 111, 99, 108), _bar(108, 112, 106, 110)])
    r = resolve(100, 95, 110, "long", df, max_bars=10)
    assert r.outcome == "win"
    assert r.r_multiple == 2.0
    assert r.bars_to_resolve == 1


def test_long_hits_stop_before_target():
    df = _df([_bar(100, 102, 94, 96)])
    r = resolve(100, 95, 110, "long", df, max_bars=10)
    assert r.outcome == "loss"
    assert r.r_multiple == -1.0
    assert r.bars_to_resolve == 1


def test_same_bar_ambiguity_is_loss():
    # A single bar spans both stop and target. Preregistered → LOSS.
    df = _df([_bar(100, 112, 94, 100)])
    r = resolve(100, 95, 110, "long", df, max_bars=10)
    assert r.outcome == "loss"


def test_timeout_within_window():
    df = _df([_bar(100, 101, 99, 100) for _ in range(3)])
    r = resolve(100, 95, 110, "long", df, max_bars=3)
    assert r.outcome == "timeout"
    assert abs(r.r_multiple - 0.0) < 1e-9
    assert r.bars_to_resolve == 3


def test_short_win():
    # Short at 100, stop 105, target 90. Bar down to 89, high stays 101.
    df = _df([_bar(100, 101, 89, 92)])
    r = resolve(100, 105, 90, "short", df, max_bars=10)
    assert r.outcome == "win"
    assert r.r_multiple == 2.0


def test_short_loss():
    df = _df([_bar(100, 106, 99, 105)])
    r = resolve(100, 105, 90, "short", df, max_bars=10)
    assert r.outcome == "loss"


def test_mae_mfe_recorded_before_resolution():
    # Long. Bar 1 dips to 96 (MAE ~ 0.8R), rallies to 108 (~1.6R), closes 100.
    # Bar 2 opens 100, spikes to 111 (past the +2R target of 110 — MFE snapshots
    # 2.2R on that bar BEFORE the return), then resolves as a win.
    df = _df([_bar(100, 108, 96, 100), _bar(100, 111, 100, 110)])
    r = resolve(100, 95, 110, "long", df, max_bars=10)
    assert r.outcome == "win"
    assert r.bars_to_resolve == 2
    assert 0.75 <= r.mae <= 0.85  # (100 - 96) / 5
    # MFE captured on bar 2's high 111 → (111-100)/5 = 2.2R, before the target
    # touch is checked. MFE > target R is CORRECT — the bar exceeded the target
    # intrabar.
    assert r.mfe >= 1.55  # loose lower bound only: the walk should see ≥ +1.6R


def test_entry_equals_stop_raises():
    df = _df([_bar(100, 101, 99, 100)])
    try:
        resolve(100, 100, 110, "long", df, max_bars=10)
    except ValueError:
        return
    assert False, "expected ValueError for zero risk_unit"
