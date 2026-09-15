"""+2R-before-−1R walker.

Given a preregistered (entry, stop, target, side) and a forward-only slice of
bars, walk until first-touch of target or stop. Returns outcome, r_multiple,
MAE, MFE, bars_to_resolve.

Same-bar ambiguity: if a single bar spans BOTH stop and target, we call it
LOSS. Conservative; documented in PREREGISTRATION.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd


Outcome = Literal["win", "loss", "timeout"]


@dataclass(frozen=True)
class Resolution:
    outcome: Outcome
    r_multiple: float
    bars_to_resolve: int
    mae: float
    mfe: float


def _r_at_price(price: float, entry: float, risk_unit: float, side: str) -> float:
    """R-multiple of `price` relative to entry, direction-aware."""
    if side == "long":
        return (price - entry) / risk_unit
    return (entry - price) / risk_unit


def resolve(
    entry: float,
    stop: float,
    target: float,
    side: str,
    bars_fwd: pd.DataFrame,
    max_bars: int = 30,
) -> Resolution:
    """`bars_fwd` must be strictly bars AFTER t0. Function does not read t0."""
    if side not in ("long", "short"):
        raise ValueError(f"side must be 'long' or 'short', got {side!r}")
    if len(bars_fwd) == 0:
        return Resolution("timeout", 0.0, 0, 0.0, 0.0)

    risk_unit = abs(entry - stop)
    if risk_unit == 0:
        raise ValueError("entry == stop; risk unit is zero, cannot resolve")

    mae = 0.0  # worst adverse excursion in R (positive number = worse)
    mfe = 0.0  # best favorable excursion in R

    for i, (_, bar) in enumerate(bars_fwd.head(max_bars).iterrows()):
        hi, lo = float(bar["high"]), float(bar["low"])

        if side == "long":
            r_hi = _r_at_price(hi, entry, risk_unit, side)  # favorable
            r_lo = _r_at_price(lo, entry, risk_unit, side)  # adverse (negative)
            hit_target = hi >= target
            hit_stop = lo <= stop
        else:
            r_hi = _r_at_price(lo, entry, risk_unit, side)  # favorable for short
            r_lo = _r_at_price(hi, entry, risk_unit, side)  # adverse for short
            hit_target = lo <= target
            hit_stop = hi >= stop

        mfe = max(mfe, r_hi)
        mae = max(mae, -r_lo)  # store MAE as a positive number

        if hit_target and hit_stop:
            # Same-bar ambiguity → LOSS (preregistered conservative choice)
            return Resolution("loss", -1.0, i + 1, mae, mfe)
        if hit_stop:
            return Resolution("loss", -1.0, i + 1, mae, mfe)
        if hit_target:
            return Resolution("win", 2.0, i + 1, mae, mfe)

    # Timeout: record r_multiple at the LAST bar's close
    last_close = float(bars_fwd.iloc[min(len(bars_fwd), max_bars) - 1]["close"])
    r_at_close = _r_at_price(last_close, entry, risk_unit, side)
    return Resolution("timeout", r_at_close, min(len(bars_fwd), max_bars), mae, mfe)
