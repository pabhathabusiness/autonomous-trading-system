"""Level provenance tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.levels import Level, levels_at, most_recent_breakout, next_opposing_level, _round_grid_near


def _mk_df(highs, lows, closes, opens=None, volumes=None):
    n = len(highs)
    opens = opens if opens is not None else closes
    volumes = volumes if volumes is not None else [1_000_000] * n
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=pd.date_range("2023-01-01", periods=n, freq="D"),
    )


def test_round_grid_scales_with_price():
    assert _round_grid_near(5.3) == [5.0, 5.5]
    assert _round_grid_near(83) == [80, 85]
    assert _round_grid_near(453) == [450, 460]
    assert _round_grid_near(750) == [750, 775]
    assert _round_grid_near(1234) == [1200, 1250]


def test_levels_include_all_provenance_types_for_full_history():
    # Build 200 bars with a clear swing high in the middle and 3 spikes at ~100
    n = 200
    highs = np.full(n, 96.0)
    lows = np.full(n, 94.0)
    closes = np.full(n, 95.0)
    # Swing pivot at index 20
    highs[20] = 100.0
    highs[19] = 97.0; highs[21] = 97.0
    # Horizontal resistance cluster: three touches at ~100 spanning 60 bars
    for j, hp in [(60, 100.2), (100, 99.9), (140, 100.1)]:
        highs[j] = hp
    df = _mk_df(list(highs), list(lows), list(closes))
    lvls = levels_at(df, t=180)
    types = {lv.level_type for lv in lvls}
    assert "swing_pivot" in types
    assert "horizontal_resistance" in types or "horizontal_support" in types  # at least one horiz
    assert "round_number" in types
    assert any(lt.startswith("prior_") for lt in types)


def test_levels_at_no_lookahead():
    n = 200
    highs = np.linspace(95, 105, n)
    lows = highs - 1
    closes = highs - 0.5
    df = _mk_df(list(highs), list(lows), list(closes))
    t = 100
    lvls_t = levels_at(df, t)
    # Mutate bars > t and re-scan; result at t must be unchanged.
    df2 = df.copy()
    df2.iloc[t + 1:, 0] = -9999.0  # open
    df2.iloc[t + 1:, 1] = -9999.0  # high
    df2.iloc[t + 1:, 2] = -9999.0  # low
    df2.iloc[t + 1:, 3] = -9999.0  # close
    lvls_t2 = levels_at(df2, t)
    # Compare sorted (price, level_type) tuples
    a = sorted((round(l.price, 4), l.level_type) for l in lvls_t)
    b = sorted((round(l.price, 4), l.level_type) for l in lvls_t2)
    assert a == b


def test_most_recent_breakout_picks_recentmost():
    # Bar 50 is a level at 100; close 51 = 101 (breakout); close 60 = 99; close 61 = 102 (later breakout)
    n = 80
    highs = np.full(n, 96.0); lows = np.full(n, 94.0); closes = np.full(n, 95.0)
    closes[51] = 101; closes[52] = 99; closes[53] = 98
    closes[60] = 99; closes[61] = 102  # more recent breakout
    df = _mk_df(list(highs), list(lows), list(closes))
    levels = [Level(price=100.0, level_type="swing_pivot", formed_at=df.index[20],
                    side="above", provenance={})]
    hit = most_recent_breakout(df, t=62, levels=levels, side="above", max_age_bars=20)
    assert hit is not None
    lvl, age = hit
    assert lvl.price == 100.0
    assert age == 0  # bar t-1 = 61 was the breakout


def test_next_opposing_level_picks_nearest_above_for_long():
    levels = [
        Level(102, "round_number", None, "above", {}),
        Level(105, "swing_pivot", None, "above", {}),
        Level(90, "prior_day_low", None, "below", {}),
    ]
    nxt = next_opposing_level(levels, reference_price=100.0, direction="long")
    assert nxt is not None and nxt.price == 102
    nxt_short = next_opposing_level(levels, reference_price=100.0, direction="short")
    assert nxt_short is not None and nxt_short.price == 90
