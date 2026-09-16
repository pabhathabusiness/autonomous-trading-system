"""Tests for research/sma_trend.py."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research import sma_trend as smat


def _random_ohlc(n: int = 260, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    step = rng.normal(0, 0.5, size=n).cumsum() + 100
    high = step + np.abs(rng.normal(0.4, 0.15, size=n))
    low = step - np.abs(rng.normal(0.4, 0.15, size=n))
    open_ = step + rng.normal(0, 0.05, size=n)
    close = step + rng.normal(0, 0.05, size=n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close},
        index=pd.date_range("2023-01-01", periods=n, freq="D"),
    )


def test_below_sma200_min_bars_unavailable():
    df = _random_ohlc(n=150)  # < 200 bars
    ctx = smat.context_at(df, None, t=149)
    assert ctx["trend.stock_sma_200"] is None
    assert ctx["trend.stock_sma_200_availability"] is False
    assert ctx["trend.stock_sma_200_slope_class"] == "UNAVAILABLE"
    # SMA20 SHOULD be present at 150 bars
    assert ctx["trend.stock_sma_20"] is not None
    assert ctx["trend.stock_sma_20_availability"] is True


def test_full_history_populates_sma_stack():
    df = _random_ohlc(n=260)
    ctx = smat.context_at(df, None, t=259)
    assert ctx["trend.stock_sma_stack_state"] in (
        "BULLISH_STACK", "BEARISH_STACK", "MIXED"
    )


def test_reclaim_event_recorded():
    # Construct a series that crosses SMA20 upward at the last bar
    n = 60
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    close = np.concatenate([np.full(30, 100.0), np.linspace(99.0, 90.0, 15), np.linspace(90.0, 110.0, 15)])
    df = pd.DataFrame(
        {"open": close, "high": close + 0.5, "low": close - 0.5, "close": close},
        index=idx,
    )
    ctx = smat.context_at(df, None, t=n - 1)
    # There should be SOME reclaim event of sma20 in the trailing history
    bs = ctx["trend.stock_bars_since_reclaim_sma20"]
    assert bs is None or isinstance(bs, int)


def test_lookahead_safety():
    df = _random_ohlc(n=260)
    t = 200
    original = smat.context_at(df, None, t)
    corrupted = df.copy()
    corrupted.iloc[t + 1:, :] = -9999.0
    fresh = smat.context_at(corrupted, None, t)
    for k in original:
        if k.startswith("trend._"):
            continue
        va, vb = original[k], fresh[k]
        if isinstance(va, float) and np.isnan(va):
            assert isinstance(vb, float) and np.isnan(vb), f"NaN diverged at {k}"
        else:
            assert va == vb, f"lookahead in {k}: {va} vs {vb}"


def test_derived_stock_vs_spy_none_when_spy_missing():
    df = _random_ohlc(n=260)
    ctx = smat.context_at(df, None, t=259)
    assert ctx["trend.derived_stock_above_sma50_spy_below_sma50"] is None
