"""+2R-before-−1R walker.

Outcomes (preregistered v0.2): WIN / LOSS / AMBIGUOUS / TIMEOUT.

AMBIGUOUS = a single bar's range spans BOTH stop and target. First-touch order
is unknowable from OHLC and is NOT coerced. The reporter carries this through
as a first-class category and derives conservative / optimistic sensitivity
bounds separately.

Entry-gap classification is a SEPARATE concern handled by classify_entry_gap()
below; the resolver takes the walk as given.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd


Outcome = Literal["win", "loss", "ambiguous", "timeout"]


@dataclass(frozen=True)
class Resolution:
    outcome: Outcome
    r_multiple: float               # canonical: win=+2, loss=-1, ambiguous=NaN, timeout=(close-entry)/risk_unit
    r_multiple_conservative: float  # ambiguous → -1, else same as r_multiple
    r_multiple_optimistic: float    # ambiguous → +2, else same as r_multiple
    bars_to_resolve: int
    mae: float                       # positive R
    mfe: float                       # positive R (favorable)
    resolving_bar_offset: int | None  # 0-indexed bar within walk that produced the outcome (None for timeout)


def _r_at_price(price: float, entry: float, risk_unit: float, side: str) -> float:
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
    """`bars_fwd` must be strictly forward bars starting AT the entry bar
    (bar t0 + entry_bar_offset from the caller). Does NOT re-check entry gap;
    the caller has already classified that and decided whether to include this
    occurrence in the primary set."""
    if side not in ("long", "short"):
        raise ValueError(f"side must be 'long' or 'short', got {side!r}")
    if len(bars_fwd) == 0:
        return Resolution("timeout", 0.0, 0.0, 0.0, 0, 0.0, 0.0, None)

    risk_unit = abs(entry - stop)
    if risk_unit == 0:
        raise ValueError("entry == stop; risk unit is zero, cannot resolve")

    mae = 0.0
    mfe = 0.0
    n = min(len(bars_fwd), max_bars)

    for i in range(n):
        bar = bars_fwd.iloc[i]
        hi, lo = float(bar["high"]), float(bar["low"])

        if side == "long":
            r_hi = _r_at_price(hi, entry, risk_unit, side)   # favorable
            r_lo = _r_at_price(lo, entry, risk_unit, side)   # adverse
            hit_target = hi >= target
            hit_stop = lo <= stop
        else:
            r_hi = _r_at_price(lo, entry, risk_unit, side)   # favorable for short
            r_lo = _r_at_price(hi, entry, risk_unit, side)   # adverse for short
            hit_target = lo <= target
            hit_stop = hi >= stop

        mfe = max(mfe, r_hi)
        mae = max(mae, -r_lo)

        if hit_target and hit_stop:
            # First-touch unknowable — record honestly.
            return Resolution(
                outcome="ambiguous",
                r_multiple=float("nan"),
                r_multiple_conservative=-1.0,
                r_multiple_optimistic=2.0,
                bars_to_resolve=i + 1,
                mae=mae,
                mfe=mfe,
                resolving_bar_offset=i,
            )
        if hit_stop:
            return Resolution("loss", -1.0, -1.0, -1.0, i + 1, mae, mfe, i)
        if hit_target:
            return Resolution("win", 2.0, 2.0, 2.0, i + 1, mae, mfe, i)

    last_close = float(bars_fwd.iloc[n - 1]["close"])
    r_at_close = _r_at_price(last_close, entry, risk_unit, side)
    return Resolution("timeout", r_at_close, r_at_close, r_at_close, n, mae, mfe, None)


# --------------------------------------------------------------------- gap
GapFlag = Literal["clean", "gap_through_stop", "gap_through_target", "above_but_reachable"]


def classify_entry_gap(entry_open: float, stop: float, target: float, side: str) -> GapFlag:
    """Classify the entry bar's OPEN vs the preregistered stop and target.

    Since the entry IS the open (by preregistration), a gap can only manifest
    as the open falling on the wrong side of stop or target. The
    `above_but_reachable` category is reserved for short-side symmetry and
    for future non-open entries.
    """
    if side == "long":
        if entry_open <= stop:
            return "gap_through_stop"
        if entry_open >= target:
            return "gap_through_target"
        return "clean"
    # short
    if entry_open >= stop:
        return "gap_through_stop"
    if entry_open <= target:
        return "gap_through_target"
    return "clean"
