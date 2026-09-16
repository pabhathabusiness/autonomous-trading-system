"""Tests for research/momentum.py — MACD raw + state + causality."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research import momentum as mom


def _random_ohlc(n: int = 100, seed: int = 5) -> pd.DataFrame:
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
    df = _random_ohlc(n=30)  # 30 < _MIN_BARS 38
    ctx = mom.context_at(df, t=29)
    assert ctx["momentum._availability"] is False
    assert ctx["momentum.macd_state"] == "UNAVAILABLE"
    assert ctx["momentum.macd_hist"] is None


def test_full_history_available():
    df = _random_ohlc(n=100)
    ctx = mom.context_at(df, t=99)
    assert ctx["momentum._availability"] is True
    assert ctx["momentum.macd_state"] in (
        "BULLISH_EXPANDING", "BULLISH_FADING",
        "BEARISH_EXPANDING", "BEARISH_FADING",
        "NEUTRAL", "UNKNOWN",
    )


def test_lookahead_safety():
    df = _random_ohlc(n=120)
    t = 80
    original = mom.context_at(df, t)
    corrupted = df.copy()
    corrupted.iloc[t + 1:, :] = -9999.0
    fresh = mom.context_at(corrupted, t)
    for k in original:
        if k.startswith("momentum._"):
            continue
        assert original[k] == fresh[k], f"lookahead at {k}"
