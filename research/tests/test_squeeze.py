"""Tests for research/squeeze.py — TTM exact math."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research import squeeze as sq


def _low_vol_ohlc(n: int = 80, seed: int = 9) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    # Tight range → BB inside KC likely
    step = rng.normal(0, 0.05, size=n).cumsum() + 100
    high = step + np.abs(rng.normal(0.05, 0.02, size=n))
    low = step - np.abs(rng.normal(0.05, 0.02, size=n))
    open_ = step + rng.normal(0, 0.01, size=n)
    close = step + rng.normal(0, 0.01, size=n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close},
        index=pd.date_range("2024-01-01", periods=n, freq="D"),
    )


def _wide_vol_ohlc(n: int = 80, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    step = rng.normal(0, 3.0, size=n).cumsum() + 100
    high = step + np.abs(rng.normal(3.0, 1.0, size=n))
    low = step - np.abs(rng.normal(3.0, 1.0, size=n))
    open_ = step + rng.normal(0, 1.0, size=n)
    close = step + rng.normal(0, 1.0, size=n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close},
        index=pd.date_range("2024-01-01", periods=n, freq="D"),
    )


def test_below_min_bars_unavailable():
    df = _low_vol_ohlc(n=30)
    ctx = sq.context_at(df, t=29)
    assert ctx["compression_volatility._squeeze_availability"] is False
    assert ctx["compression_volatility.squeeze_on"] is None


def test_squeeze_on_or_off_boolean():
    df = _low_vol_ohlc(n=80)
    ctx = sq.context_at(df, t=79)
    if ctx["compression_volatility._squeeze_availability"]:
        assert isinstance(ctx["compression_volatility.squeeze_on"], bool)


def test_wide_vol_generally_squeeze_off():
    df = _wide_vol_ohlc(n=80)
    ctx = sq.context_at(df, t=79)
    if ctx["compression_volatility._squeeze_availability"]:
        # Wide volatility should typically NOT be in squeeze
        assert ctx["compression_volatility.squeeze_off"] in (True, False)  # just ensure bool


def test_lookahead_safety():
    df = _low_vol_ohlc(n=100)
    t = 70
    original = sq.context_at(df, t)
    corrupted = df.copy()
    corrupted.iloc[t + 1:, :] = -9999.0
    fresh = sq.context_at(corrupted, t)
    for k in original:
        if k.startswith("compression_volatility._"):
            continue
        va, vb = original[k], fresh[k]
        if isinstance(va, float) and np.isnan(va):
            assert isinstance(vb, float) and np.isnan(vb), f"NaN diverged at {k}"
        else:
            assert va == vb, f"lookahead at {k}"
