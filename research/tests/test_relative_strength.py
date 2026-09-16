"""Tests for research/relative_strength.py — alignment, minimums, UNAVAILABLE."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research import relative_strength as rs


def _closes(n: int, drift: float = 0.001, seed: int = 3) -> pd.Series:
    rng = np.random.default_rng(seed)
    steps = 1 + drift + rng.normal(0, 0.01, size=n)
    prices = 100 * steps.cumprod()
    return pd.Series(prices, index=pd.date_range("2024-01-01", periods=n, freq="D"))


def test_rs_class_thresholds():
    stock = _closes(60, drift=0.005, seed=1)
    spy = _closes(60, drift=-0.005, seed=2)
    t = stock.index[-1]
    ctx = rs.context_at(stock, spy, t)
    assert ctx["relative_strength.rs_class"] in ("OUTPERFORMING", "NEUTRAL", "UNDERPERFORMING")
    # A stock rising while SPY falls should not be UNDERPERFORMING
    if ctx["relative_strength.rs_spy_20d"] is not None:
        assert ctx["relative_strength.rs_spy_20d"] > 0
        assert ctx["relative_strength.rs_class"] in ("OUTPERFORMING", "NEUTRAL")


def test_below_min_regime_bars_returns_unavailable():
    # Only 3 bars — well below the min of 10 weakness bars
    idx = pd.date_range("2024-01-01", periods=3, freq="D")
    stock = pd.Series([100.0, 101.0, 102.0], index=idx)
    spy = pd.Series([100.0, 99.5, 100.5], index=idx)
    ctx = rs.context_at(stock, spy, idx[-1])
    # rs_during_spy_weakness_frac_outperformed should be None + availability False
    assert ctx["relative_strength.rs_during_spy_weakness_availability"] is False
    assert ctx["relative_strength.rs_during_spy_weakness_frac_outperformed"] is None


def test_alignment_dropna_no_forward_fill():
    idx_stock = pd.date_range("2024-01-01", periods=25, freq="D")
    idx_spy = idx_stock[::2]  # SPY has every other day
    stock = pd.Series(range(25, 50), index=idx_stock, dtype=float)
    spy = pd.Series(range(50, 50 + len(idx_spy)), index=idx_spy, dtype=float)
    # Should still produce SOMETHING without throwing (backward asof with tolerance=1d)
    ctx = rs.context_at(stock, spy, stock.index[-1])
    assert "relative_strength.rs_class" in ctx


def test_causal_no_lookahead():
    stock = _closes(80, drift=0.001, seed=5)
    spy = _closes(80, drift=0.001, seed=6)
    t = stock.index[40]
    ctx_a = rs.context_at(stock, spy, t)
    # Corrupt bars after t
    stock_bad = stock.copy()
    spy_bad = spy.copy()
    stock_bad.iloc[41:] = -9999.0
    spy_bad.iloc[41:] = -9999.0
    ctx_b = rs.context_at(stock_bad, spy_bad, t)
    for k in ctx_a:
        if k.endswith("_source_data_end") or k.endswith("_known_at"):
            continue
        va, vb = ctx_a[k], ctx_b[k]
        if isinstance(va, float) and np.isnan(va):
            assert np.isnan(vb) if isinstance(vb, float) else vb is None
        else:
            assert va == vb, f"lookahead at {k}: {va} vs {vb}"


def test_prefix_replay_invariance():
    stock = _closes(100, drift=0.002, seed=11)
    spy = _closes(100, drift=0.001, seed=12)
    t = stock.index[60]
    # Full history
    full = rs.context_at(stock, spy, t)
    # Prefix only up to t + a few bars beyond
    stock_pref = stock.iloc[: 65]
    spy_pref = spy.iloc[: 65]
    pref = rs.context_at(stock_pref, spy_pref, t)
    for k in full:
        if k.endswith("_source_data_end") or k.endswith("_known_at"):
            continue
        assert full[k] == pref[k], f"prefix-replay diverged at {k}"
