"""BREAKOUT_INSIDE_DAY_CONTINUATION — long only.

See PREREGISTRATION.md for full definitions. Every threshold used here is
locked and referenced by name.

Scan:
  for each bar t in the history (starting once we have enough warmup):
    if bar t is an inside day (high_t <= high_{t-1} AND low_t >= low_{t-1}):
      freeze features at t
      also compute detector-specific frozen state:
         - was_breakout_at_tm1: did close_{t-1} cross a known-untouched
           swing high (fractal, order=3, untouched for >= 20 bars prior)?
         - broken_pivot: the price of that swing high (or NaN if not)
         - holding_above_at_t: close_t > broken_pivot (only meaningful when
           was_breakout_at_tm1)
      compute entry / stop / target
      emit Occurrence (entry_bar_offset = 1  → entry at open of t+1)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import features as feat_mod
from .. import math_utils as mu
from ._base import Occurrence


class BreakoutInsideDayContinuation:
    name = "BREAKOUT_INSIDE_DAY_CONTINUATION"
    side = "long"

    # Warmup: need at least 60 bars for BB percentile + 3 order for pivots + 20
    # for untouched requirement + 50 for EMA(50) → be generous.
    WARMUP = 80

    # Locked knobs (see PREREGISTRATION.md)
    PIVOT_ORDER = 3
    PIVOT_LOOKBACK = 60
    UNTOUCHED_BARS = 20
    STOP_ATR_PAD = 0.1

    def scan(self, symbol: str, df: pd.DataFrame) -> list[Occurrence]:
        df = df.copy()
        _validate_ohlc_columns(df)
        n = len(df)
        if n < self.WARMUP + 2:  # need at least t+1 available too
            return []

        occ: list[Occurrence] = []
        atr14 = mu.atr(df, 14).values

        # Anchored pivot flags (True at the bar of formation). Visibility to a
        # given evaluation bar t' is enforced downstream via PIVOT_ORDER, not by
        # a shifted series — the shifted series was confusing price lookups.
        ph_flags, _ = mu.fractal_pivots(df, order=self.PIVOT_ORDER)
        highs = df["high"]

        for t in range(self.WARMUP, n - 1):  # t+1 must exist for entry
            prev = df.iloc[t - 1]
            cur = df.iloc[t]
            if not (cur["high"] <= prev["high"] and cur["low"] >= prev["low"]):
                continue  # not an inside day

            # Detector-specific frozen state
            broken_pivot, was_breakout = _breakout_context(
                df, ph_flags=ph_flags, highs=highs, t=t,
                pivot_lookback=self.PIVOT_LOOKBACK,
                untouched_bars=self.UNTOUCHED_BARS,
                order=self.PIVOT_ORDER,
            )
            holding_above = bool(
                was_breakout and pd.notna(broken_pivot) and cur["close"] > broken_pivot
            )

            # Freeze features (bar-close of t)
            features = feat_mod.freeze_at(df, t)
            features.update({
                "was_breakout_at_tm1": bool(was_breakout),
                "broken_pivot": float(broken_pivot) if pd.notna(broken_pivot) else None,
                "holding_above_at_t": holding_above,
            })

            # Entry / stop / target
            entry = float(df.iloc[t + 1]["open"])  # next bar open
            stop_base = float(min(cur["low"], prev["low"]))
            atr_t = atr14[t] if t < len(atr14) else np.nan
            if not np.isfinite(atr_t) or atr_t <= 0:
                continue  # unresolvable stop
            stop = stop_base - self.STOP_ATR_PAD * float(atr_t)
            risk_unit = entry - stop
            if risk_unit <= 0:
                continue  # entry below stop (gap), unresolvable
            target = entry + 2.0 * risk_unit

            occ.append(Occurrence(
                symbol=symbol,
                t0=df.index[t],
                entry=entry,
                stop=stop,
                target=target,
                side="long",
                features=features,
                entry_bar_offset=1,
            ))
        return occ


def _breakout_context(
    df: pd.DataFrame,
    *,
    ph_flags: pd.Series,
    highs: pd.Series,
    t: int,
    pivot_lookback: int,
    untouched_bars: int,
    order: int,
) -> tuple[float, bool]:
    """Did close_{t-1} cross a known-untouched swing high?

    Rules (preregistered):
      - `ph_flags` is anchored (True at bar of pivot formation). A pivot at
        bar i is only VISIBLE at bar i + order (needs `order` future bars).
      - "untouched" = no close from `piv_iloc + 1` to `t - 2` (inclusive) was
        ≥ pivot_high for at least `untouched_bars` bars total.
      - "crossed" = close_{t-1} > pivot_high AND close_{t-2} <= pivot_high

    Returns (broken_pivot_price, was_breakout).
    """
    if t < 2:
        return (float("nan"), False)

    prev = df.iloc[t - 1]
    prev_prev = df.iloc[t - 2]
    close_prev = float(prev["close"])
    close_prev_prev = float(prev_prev["close"])

    # Bar t-1 is the crossing bar. It sees pivots formed AT OR BEFORE bar
    # (t - 1) - order (needs `order` bars past the pivot bar to confirm).
    lo = max(0, t - 1 - pivot_lookback)
    hi = (t - 1) - order  # candidates must be visible by bar t-1
    if hi <= lo:
        return (float("nan"), False)

    candidate_ilocs = [i for i in range(lo, hi) if bool(ph_flags.iloc[i])]
    if not candidate_ilocs:
        return (float("nan"), False)

    # Highest unbroken level in the window wins.
    candidates = sorted(
        [(float(highs.iloc[i]), i) for i in candidate_ilocs],
        key=lambda x: x[0], reverse=True,
    )
    for piv_price, piv_iloc in candidates:
        touched_window = df["close"].iloc[piv_iloc + 1: t - 1]
        if (touched_window >= piv_price).any():
            continue  # touched by an earlier close → not a fresh breakout at t-1
        if (t - 1) - piv_iloc < untouched_bars:
            continue
        if close_prev > piv_price and close_prev_prev <= piv_price:
            return (float(piv_price), True)
        # Highest unbroken level did NOT cross at t-1. A lower unbroken level
        # crossing does not qualify as a fresh breakout of this window.
        return (float(piv_price), False)
    return (float("nan"), False)


def _validate_ohlc_columns(df: pd.DataFrame) -> None:
    required = {"open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"df missing OHLC columns: {sorted(missing)}")
