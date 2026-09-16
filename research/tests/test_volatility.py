"""Tests for research/volatility.py — extended BB + composite label."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research import volatility as vol


def _random_ohlc(n: int = 90, seed: int = 4) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    step = rng.normal(0, 0.5, size=n).cumsum() + 100
    high = step + np.abs(rng.normal(0.4, 0.15, size=n))
    low = step - np.abs(rng.normal(0.4, 0.15, size=n))
    open_ = step + rng.normal(0, 0.05, size=n)
    close = step + rng.normal(0, 0.05, size=n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close},
        index=pd.date_range("2024-01-01", periods=n, freq="D"),
    )


def test_below_min_bars_unavailable():
    df = _random_ohlc(n=40)
    ctx = vol.context_at(df, t=39)
    assert ctx["compression_volatility._bb_availability"] is False
    assert ctx["compression_volatility.bb_state"] == "UNAVAILABLE"
    assert ctx["compression_volatility.volatility_label"] == "UNAVAILABLE"


def test_full_bb_context_available():
    df = _random_ohlc(n=90)
    ctx = vol.context_at(df, t=89)
    assert ctx["compression_volatility._bb_availability"] is True
    assert ctx["compression_volatility.bb_state"] in ("COMPRESSION", "EXPANSION", "NORMAL")
    assert ctx["compression_volatility.volatility_label"] in (
        "DEEP_COMPRESSION", "COMPRESSION", "NORMAL", "EXPANDING", "HIGH_VOLATILITY"
    )


def test_percent_b_in_range():
    df = _random_ohlc(n=90)
    ctx = vol.context_at(df, t=89)
    if ctx["compression_volatility.bb_percent_b"] is not None:
        # Not strictly bounded (price can breach bands) but should be finite
        assert np.isfinite(ctx["compression_volatility.bb_percent_b"])


def test_lookahead_safety():
    df = _random_ohlc(n=120)
    t = 80
    original = vol.context_at(df, t)
    corrupted = df.copy()
    corrupted.iloc[t + 1:, :] = -9999.0
    fresh = vol.context_at(corrupted, t)
    for k in original:
        if k.startswith("compression_volatility._"):
            continue
        va, vb = original[k], fresh[k]
        if isinstance(va, float) and np.isnan(va):
            assert isinstance(vb, float) and np.isnan(vb), f"NaN diverged at {k}"
        else:
            assert va == vb, f"lookahead at {k}"
