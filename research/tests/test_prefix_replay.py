"""Universal prefix-replay + append-future invariance test.

For each context layer, running `context_at` at bar t of a truncated
history (df[:t+K+1] for various K) must produce identical output to
running it at t on the full history. If any output differs, the layer
is peeking at future bars.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research import supply_demand as sd
from research import relative_strength as rs
from research import sma_trend as smat
from research import momentum as mom
from research import squeeze as sq
from research import volatility as vol
from research import regime as rg


def _random_ohlc(n: int = 300, seed: int = 42) -> pd.DataFrame:
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


def _closes(n: int, seed: int) -> pd.Series:
    rng = np.random.default_rng(seed)
    steps = 1 + rng.normal(0, 0.01, size=n)
    prices = 100 * steps.cumprod()
    return pd.Series(prices, index=pd.date_range("2023-01-01", periods=n, freq="D"))


def _eq(a, b) -> bool:
    if isinstance(a, float) and np.isnan(a):
        return isinstance(b, float) and np.isnan(b)
    return a == b


@pytest.mark.parametrize("t,K", [(150, 0), (150, 30), (200, 0), (200, 50)])
def test_sma_prefix_replay(t: int, K: int):
    df = _random_ohlc(n=300)
    truncated = df.iloc[: t + K + 1]
    full = smat.context_at(df, None, t=t)
    prefix = smat.context_at(truncated, None, t=t)
    for k in full:
        if k.startswith("trend._"):
            continue
        assert _eq(full[k], prefix[k]), f"sma prefix-replay diverged at {k}"


@pytest.mark.parametrize("t,K", [(80, 0), (80, 20), (100, 0), (100, 50)])
def test_momentum_prefix_replay(t: int, K: int):
    df = _random_ohlc(n=200)
    truncated = df.iloc[: t + K + 1]
    full = mom.context_at(df, t=t)
    prefix = mom.context_at(truncated, t=t)
    for k in full:
        if k.startswith("momentum._"):
            continue
        assert _eq(full[k], prefix[k]), f"momentum prefix-replay diverged at {k}"


@pytest.mark.parametrize("t,K", [(80, 0), (80, 20), (100, 0), (100, 40)])
def test_squeeze_prefix_replay(t: int, K: int):
    df = _random_ohlc(n=200)
    truncated = df.iloc[: t + K + 1]
    full = sq.context_at(df, t=t)
    prefix = sq.context_at(truncated, t=t)
    for k in full:
        if k.startswith("compression_volatility._"):
            continue
        assert _eq(full[k], prefix[k]), f"squeeze prefix-replay diverged at {k}"


@pytest.mark.parametrize("t,K", [(90, 0), (90, 30), (120, 0), (120, 50)])
def test_volatility_prefix_replay(t: int, K: int):
    df = _random_ohlc(n=250)
    truncated = df.iloc[: t + K + 1]
    full = vol.context_at(df, t=t)
    prefix = vol.context_at(truncated, t=t)
    for k in full:
        if k.startswith("compression_volatility._"):
            continue
        assert _eq(full[k], prefix[k]), f"volatility prefix-replay diverged at {k}"


@pytest.mark.parametrize("t_offset,K", [(60, 0), (60, 20), (80, 0), (80, 40)])
def test_relative_strength_prefix_replay(t_offset: int, K: int):
    stock = _closes(150, seed=17)
    spy = _closes(150, seed=18)
    t = stock.index[t_offset]
    full = rs.context_at(stock, spy, t)
    stock_pref = stock.iloc[: t_offset + K + 1]
    spy_pref = spy.iloc[: t_offset + K + 1]
    prefix = rs.context_at(stock_pref, spy_pref, t)
    for k in full:
        if k.startswith("relative_strength._"):
            continue
        assert _eq(full[k], prefix[k]), f"RS prefix-replay diverged at {k}"


@pytest.mark.parametrize("t_offset,K", [(80, 0), (80, 30), (120, 0), (120, 40)])
def test_market_regime_prefix_replay(t_offset: int, K: int):
    spy = _random_ohlc(n=200)
    t = spy.index[t_offset]
    full = rg.market_context_at(spy, t)
    spy_pref = spy.iloc[: t_offset + K + 1]
    prefix = rg.market_context_at(spy_pref, t)
    for k in full:
        if k.startswith("market._"):
            continue
        assert _eq(full[k], prefix[k]), f"market prefix-replay diverged at {k}"


def test_supply_demand_evaluate_at_prefix_replay():
    df = _random_ohlc(n=200)
    zones = sd.detect_zones("TEST", df.iloc[:120])
    if not zones:
        pytest.skip("no zones from random data")
    t = 100
    # evaluate_at on full df vs on prefix
    full = sd.evaluate_at(zones, df, t=t)
    prefix = sd.evaluate_at(zones, df.iloc[:t + 40], t=t)
    for a, b in zip(full, prefix):
        assert a.active == b.active
        assert a.age_bars == b.age_bars
        assert a.touches_since_creation == b.touches_since_creation
