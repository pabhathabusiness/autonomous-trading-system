"""Freeze-features-at-T0. Every extractor here is guaranteed lookahead-free
by the tests in `research/tests/test_no_lookahead.py`.

The convention: given a bar index `t` in a full history `df`, extractors read
only `df.iloc[:t+1]` — never beyond. Pivots are shifted by their `order` so a
pivot at index `i` is only visible at index `i + order` (needs future bars to
confirm).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from . import math_utils as mu


def freeze_at(df: pd.DataFrame, t: int) -> dict[str, Any]:
    """Snapshot of features at close of bar `t`. Only bars ≤ t are consulted.

    Returned dict is intended to be locked and passed forward to cell
    predicates and the report — no forward mutation.
    """
    if t < 0 or t >= len(df):
        raise IndexError(f"t={t} out of range for df of length {len(df)}")
    hist = df.iloc[: t + 1]  # inclusive of t
    close = hist["close"]

    atr14 = mu.atr(hist, 14)
    atr14_t = float(atr14.iloc[-1]) if not atr14.empty and pd.notna(atr14.iloc[-1]) else np.nan

    # BB width percentile at t (percentile within trailing 60 bars)
    bbw_pct = mu.bb_width_percentile(close, period=20, lookback=60)
    bbw_pct_t = float(bbw_pct.iloc[-1]) if pd.notna(bbw_pct.iloc[-1]) else np.nan

    # ATR ratio: current ATR ÷ 60d mean ATR
    ar = mu.atr_ratio(hist, 14, 60)
    ar_t = float(ar.iloc[-1]) if pd.notna(ar.iloc[-1]) else np.nan

    # Compression: BBW in bottom quartile OR ATR ratio < 0.75
    compression = bool(
        (pd.notna(bbw_pct_t) and bbw_pct_t <= 0.25) or (pd.notna(ar_t) and ar_t < 0.75)
    )

    # MACD state
    macd_state = mu.macd_transition(close, within=3).iloc[-1]

    m = mu.macd(close)
    hist_t = float(m["hist"].iloc[-1]) if pd.notna(m["hist"].iloc[-1]) else np.nan
    hist_tm1 = float(m["hist"].iloc[-2]) if len(m) >= 2 and pd.notna(m["hist"].iloc[-2]) else np.nan
    hist_tm2 = float(m["hist"].iloc[-3]) if len(m) >= 3 and pd.notna(m["hist"].iloc[-3]) else np.nan

    fresh_reaccel_up = bool(
        pd.notna(hist_t) and pd.notna(hist_tm1) and pd.notna(hist_tm2)
        and hist_t > 0 and hist_tm1 > 0 and hist_tm2 > 0
        and abs(hist_t) > abs(hist_tm1) > abs(hist_tm2)
    )
    fresh_reaccel_dn = bool(
        pd.notna(hist_t) and pd.notna(hist_tm1) and pd.notna(hist_tm2)
        and hist_t < 0 and hist_tm1 < 0 and hist_tm2 < 0
        and abs(hist_t) > abs(hist_tm1) > abs(hist_tm2)
    )

    # EMA stacks
    stack_up = bool(mu.ema_stack_up(close).iloc[-1])
    stack_dn = bool(mu.ema_stack_down(close).iloc[-1])

    # Pivots — anchored, shifted by order so they're only visible in a
    # lookahead-safe way
    pivot_above = mu.last_pivot_above(hist, len(hist) - 1, order=3, lookback=60)
    pivot_below = mu.last_pivot_below(hist, len(hist) - 1, order=3, lookback=60)

    # Untouched swing high — did any close touch pivot_above in the last 20 bars
    # after that pivot was formed? A tighter rule (untouched for ≥20 bars) is
    # enforced by the detector itself; here we surface the raw "days_since_touch".
    days_since_touch_above = _bars_since_close_touched(close, pivot_above)
    days_since_touch_below = _bars_since_close_touched(close, pivot_below, above=False)

    # Room to next opposing pivot
    price_t = float(close.iloc[-1])
    room_above_atr = ((pivot_above - price_t) / atr14_t) if (pivot_above and pd.notna(atr14_t) and atr14_t > 0) else np.nan
    room_below_atr = ((price_t - pivot_below) / atr14_t) if (pivot_below and pd.notna(atr14_t) and atr14_t > 0) else np.nan

    # Inside-day flag (bar t inside bar t-1)
    inside_day = False
    if t >= 1:
        prev = df.iloc[t - 1]
        cur = df.iloc[t]
        inside_day = bool(cur["high"] <= prev["high"] and cur["low"] >= prev["low"])

    return {
        "price_t": price_t,
        "atr14": atr14_t,
        "bb_width_percentile": bbw_pct_t,
        "atr_ratio_60": ar_t,
        "compression": compression,
        "macd_state": macd_state,
        "hist_t": hist_t,
        "hist_tm1": hist_tm1,
        "hist_tm2": hist_tm2,
        "fresh_macd_reaccel_up": fresh_reaccel_up,
        "fresh_macd_reaccel_down": fresh_reaccel_dn,
        "ema_stack_up": stack_up,
        "ema_stack_down": stack_dn,
        "pivot_above": pivot_above,
        "pivot_below": pivot_below,
        "days_since_close_touch_above": days_since_touch_above,
        "days_since_close_touch_below": days_since_touch_below,
        "room_above_atr": room_above_atr,
        "room_below_atr": room_below_atr,
        "inside_day": inside_day,
    }


def _bars_since_close_touched(close: pd.Series, pivot: float | None, above: bool = True,
                              max_lookback: int = 120) -> int | None:
    """How many bars back until the most recent close crossed the pivot (from
    below, if `above` — i.e. a close ≥ pivot). None if never touched in
    max_lookback."""
    if pivot is None or not pd.notna(pivot):
        return None
    tail = close.tail(max_lookback)
    if above:
        hits = tail[tail >= pivot]
    else:
        hits = tail[tail <= pivot]
    if hits.empty:
        return None
    last_hit_idx = tail.index.get_loc(hits.index[-1])
    return int(len(tail) - 1 - last_hit_idx)
