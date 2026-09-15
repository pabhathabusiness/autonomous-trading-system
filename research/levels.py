"""Level detection with explicit provenance.

Three families, all with the same output type:
  - swing_pivot: fractal high/low, order=3, drawn from trailing 60 bars.
  - horizontal_resistance / horizontal_support: ≥ 3 highs/lows within a small
    tolerance of each other, spanning ≥ 10 bars, all inside trailing 90 bars.
  - known_level: round-number grid, prior-day / prior-week / prior-month
    high/low.

Each Level carries type-specific provenance so the BIDC detector can store
it verbatim on the occurrence and cell predicates can key on `level_type`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

from . import math_utils as mu


LevelType = Literal[
    "swing_pivot", "horizontal_resistance", "horizontal_support",
    "round_number", "prior_day_high", "prior_day_low",
    "prior_week_high", "prior_week_low",
    "prior_month_high", "prior_month_low",
]


@dataclass(frozen=True)
class Level:
    price: float
    level_type: LevelType
    formed_at: pd.Timestamp | None            # bar of formation for pivots; None for round numbers
    side: Literal["above", "below"]           # 'above' = resistance / breakout target for longs
    provenance: dict = field(default_factory=dict)  # type-specific metadata


def _round_grid_near(price: float) -> list[float]:
    """Return the two round numbers just below and just above `price`, using
    a step size that scales with price magnitude:
      < $10 → $0.50
      < $100 → $5
      < $500 → $10
      < $1000 → $25
      ≥ $1000 → $50
    """
    if price < 10: step = 0.5
    elif price < 100: step = 5.0
    elif price < 500: step = 10.0
    elif price < 1000: step = 25.0
    else: step = 50.0
    lo = np.floor(price / step) * step
    hi = np.ceil(price / step) * step
    if lo == hi:
        hi = lo + step
    return [float(lo), float(hi)]


def levels_at(df: pd.DataFrame, t: int, *,
              pivot_order: int = 3,
              pivot_lookback: int = 60,
              horiz_lookback: int = 90,
              horiz_min_touches: int = 3,
              horiz_tolerance_atr: float = 0.25,
              horiz_min_span_bars: int = 10) -> list[Level]:
    """All levels observable at close of bar t. Lookahead-safe by construction."""
    if t < 0 or t >= len(df):
        return []
    hist = df.iloc[: t + 1]
    atr14 = mu.atr(hist, 14)
    atr_t = float(atr14.iloc[-1]) if len(atr14) and pd.notna(atr14.iloc[-1]) else float("nan")

    levels: list[Level] = []
    price = float(hist["close"].iloc[-1])

    # ---------------------------------------------- swing pivots (known-safe)
    ph_flags, pl_flags = mu.fractal_pivots(hist, order=pivot_order)
    for j in range(max(0, len(hist) - pivot_lookback - pivot_order), len(hist) - pivot_order):
        if bool(ph_flags.iloc[j]):
            levels.append(Level(
                price=float(hist["high"].iloc[j]),
                level_type="swing_pivot",
                formed_at=hist.index[j],
                side="above" if hist["high"].iloc[j] > price else "below",
                provenance={"order": pivot_order, "bars_since_formation": len(hist) - 1 - j - pivot_order},
            ))
        if bool(pl_flags.iloc[j]):
            levels.append(Level(
                price=float(hist["low"].iloc[j]),
                level_type="swing_pivot",
                formed_at=hist.index[j],
                side="below" if hist["low"].iloc[j] < price else "above",
                provenance={"order": pivot_order, "bars_since_formation": len(hist) - 1 - j - pivot_order},
            ))

    # ------------------------------------- horizontal resistance / support
    if np.isfinite(atr_t) and atr_t > 0 and len(hist) >= horiz_lookback:
        window = hist.tail(horiz_lookback)
        tol = horiz_tolerance_atr * atr_t

        # Find cluster centers for highs and lows separately using a simple
        # greedy scan on sorted values.
        for col, is_res in (("high", True), ("low", False)):
            vals = window[col].to_numpy()
            idxs = np.arange(len(window))
            # sort by value
            order = np.argsort(vals)
            sv, si = vals[order], idxs[order]
            used = np.zeros(len(sv), dtype=bool)
            for k in range(len(sv)):
                if used[k]:
                    continue
                cluster = [k]
                for m in range(k + 1, len(sv)):
                    if used[m]:
                        continue
                    if sv[m] - sv[cluster[0]] <= tol:
                        cluster.append(m)
                    else:
                        break
                if len(cluster) >= horiz_min_touches:
                    bar_ilocs = si[cluster]
                    span = int(bar_ilocs.max() - bar_ilocs.min())
                    if span >= horiz_min_span_bars:
                        cluster_price = float(np.mean(sv[cluster]))
                        latest_bar = int(bar_ilocs.max())
                        levels.append(Level(
                            price=cluster_price,
                            level_type="horizontal_resistance" if is_res else "horizontal_support",
                            formed_at=window.index[latest_bar],
                            side="above" if cluster_price > price else "below",
                            provenance={
                                "n_touches": len(cluster),
                                "span_bars": span,
                                "tolerance_atr": horiz_tolerance_atr,
                            },
                        ))
                        for m in cluster:
                            used[m] = True

    # -------------------------------------------------- prior day / wk / mo
    daily_lookback_map = {
        "prior_day": 1,
        "prior_week": 5,     # daily bars ~ trading week
        "prior_month": 21,   # daily bars ~ trading month
    }
    for name, back in daily_lookback_map.items():
        if len(hist) > back:
            recent = hist.iloc[-back - 1: -1]  # exclude bar t itself
            if len(recent):
                levels.append(Level(
                    price=float(recent["high"].max()),
                    level_type=f"{name}_high",  # type: ignore[arg-type]
                    formed_at=recent["high"].idxmax(),
                    side="above" if recent["high"].max() > price else "below",
                    provenance={"window_bars": back},
                ))
                levels.append(Level(
                    price=float(recent["low"].min()),
                    level_type=f"{name}_low",  # type: ignore[arg-type]
                    formed_at=recent["low"].idxmin(),
                    side="below" if recent["low"].min() < price else "above",
                    provenance={"window_bars": back},
                ))

    # -------------------------------------------------------- round numbers
    for rp in _round_grid_near(price):
        levels.append(Level(
            price=rp,
            level_type="round_number",
            formed_at=None,
            side="above" if rp > price else "below",
            provenance={"grid_step": _round_grid_near(price)[1] - _round_grid_near(price)[0]},
        ))

    return levels


def most_recent_breakout(
    df: pd.DataFrame, t: int, levels: list[Level], *, side: Literal["above", "below"] = "above",
    max_age_bars: int = 20,
) -> tuple[Level, int] | None:
    """Find the level whose close-through happened most recently in the last
    `max_age_bars` bars ending at t-1 (i.e., bar of breakout ≤ t-1).

    Returns (level, breakout_age_bars) where breakout_age_bars = (t-1) - b_iloc,
    so 0 = breakout was on t-1, 1 = t-2, …. None if no such breakout.
    """
    if t < 2:
        return None
    best: tuple[Level, int] | None = None
    for lvl in levels:
        # Do NOT filter by lvl.side. `side` here means DIRECTION OF CROSSING,
        # not position of the level relative to the current close. A bullish
        # breakout crosses UP through a level that MAY have been above us at
        # formation but is now below us (or still above). The crossing check
        # inside the inner loop handles direction correctly.
        # Find the most recent breakout bar b ≤ t-1 with close_b crossing lvl.price
        # and close_{b-1} ≤ lvl.price (for above) — search backward from t-1.
        for b in range(t - 1, max(0, t - 1 - max_age_bars), -1):
            if b <= 0:
                break
            close_b = float(df["close"].iloc[b])
            close_bm1 = float(df["close"].iloc[b - 1])
            if side == "above":
                crossed = close_b > lvl.price and close_bm1 <= lvl.price
            else:
                crossed = close_b < lvl.price and close_bm1 >= lvl.price
            if crossed:
                age = (t - 1) - b
                if best is None or age < best[1]:
                    best = (lvl, age)
                break
    return best


def next_opposing_level(levels: list[Level], reference_price: float, direction: str) -> Level | None:
    """Given the entry direction, find the nearest level on the *opposite* side
    of `reference_price` that's a potential resistance/support against the
    trade. For a long trade entering at `reference_price`, we want the nearest
    level ABOVE that could cap the move — the target-side ceiling."""
    if direction == "long":
        above = [lv for lv in levels if lv.price > reference_price]
        if not above:
            return None
        return min(above, key=lambda lv: lv.price)
    below = [lv for lv in levels if lv.price < reference_price]
    if not below:
        return None
    return max(below, key=lambda lv: lv.price)
