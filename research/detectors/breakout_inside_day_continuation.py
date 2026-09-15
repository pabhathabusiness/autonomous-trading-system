"""BREAKOUT_INSIDE_DAY_CONTINUATION — long only.

v0.2 — accepts breakouts of any level provenance (swing_pivot,
horizontal_resistance, known_level). Stores level metadata + breakout age +
ATR-normalized distance + room-to-next-level in ATR and R units. Records
entry-gap classification (clean / gap_through_stop / gap_through_target).

See PREREGISTRATION.md § BREAKOUT_INSIDE_DAY_CONTINUATION for full spec.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import features as feat_mod
from .. import levels as level_mod
from .. import math_utils as mu
from ..resolve import classify_entry_gap
from ._base import Occurrence


class BreakoutInsideDayContinuation:
    name = "BREAKOUT_INSIDE_DAY_CONTINUATION"
    side = "long"

    WARMUP = 90            # enough for horizontal_lookback + pivot warmup
    PIVOT_ORDER = 3
    PIVOT_LOOKBACK = 60
    HORIZ_LOOKBACK = 90
    STOP_ATR_PAD = 0.1
    BREAKOUT_AGE_MAX = 20  # bar t-1 backwards this many bars for a "recent breakout"

    def scan(self, symbol: str, df: pd.DataFrame) -> list[Occurrence]:
        _validate_ohlc_columns(df)
        df = df.copy()
        n = len(df)
        if n < self.WARMUP + 2:
            return []

        atr14 = mu.atr(df, 14).values
        occ: list[Occurrence] = []

        for t in range(self.WARMUP, n - 1):
            prev = df.iloc[t - 1]
            cur = df.iloc[t]
            if not (cur["high"] <= prev["high"] and cur["low"] >= prev["low"]):
                continue

            # ---- level context (any provenance) at bar t (looks back only)
            all_levels = level_mod.levels_at(
                df, t,
                pivot_order=self.PIVOT_ORDER,
                pivot_lookback=self.PIVOT_LOOKBACK,
                horiz_lookback=self.HORIZ_LOOKBACK,
            )
            breakout = level_mod.most_recent_breakout(
                df, t, all_levels, side="above",
                max_age_bars=self.BREAKOUT_AGE_MAX,
            )
            if breakout is None:
                broken_level_price = float("nan")
                level_type = None
                level_formed_at = None
                level_provenance: dict = {}
                breakout_age = None
                was_breakout = False
                holding_above = False
                distance_to_level_atr = float("nan")
            else:
                lvl, breakout_age = breakout
                broken_level_price = lvl.price
                level_type = lvl.level_type
                level_formed_at = lvl.formed_at
                level_provenance = dict(lvl.provenance)
                was_breakout = True
                holding_above = float(cur["close"]) > lvl.price
                atr_t = float(atr14[t]) if t < len(atr14) else float("nan")
                if np.isfinite(atr_t) and atr_t > 0:
                    distance_to_level_atr = (float(cur["close"]) - lvl.price) / atr_t
                else:
                    distance_to_level_atr = float("nan")

            # ---- planned entry / stop / target (locked at close of bar t)
            atr_t = float(atr14[t]) if t < len(atr14) else float("nan")
            if not np.isfinite(atr_t) or atr_t <= 0:
                continue
            planned_entry = float(cur["close"])          # reference for the plan
            stop_base = float(min(cur["low"], prev["low"]))
            planned_stop = stop_base - self.STOP_ATR_PAD * atr_t
            planned_risk = planned_entry - planned_stop
            if planned_risk <= 0:
                continue                                  # unplannable
            planned_target = planned_entry + 2.0 * planned_risk

            # ---- classify actual next-bar-open against the PLAN
            actual_entry_open = float(df.iloc[t + 1]["open"])
            gap_flag = classify_entry_gap(
                entry_open=actual_entry_open,
                stop=planned_stop, target=planned_target, side="long",
            )

            # Resolver runs against the PLAN (planned_entry / planned_stop /
            # planned_target). r_multiple is scored vs the plan's risk unit so
            # a favorable-gap does NOT get free R credit; instead the diagnostic
            # gap flag is stamped and the row is excluded from primary stats.
            entry = planned_entry
            stop = planned_stop
            target = planned_target

            # ---- room to next opposing level (target side)
            next_opp = level_mod.next_opposing_level(all_levels, planned_entry, direction="long")
            room_atr = float("nan")
            room_R = float("nan")
            if next_opp is not None and np.isfinite(atr_t) and atr_t > 0:
                room_atr = (next_opp.price - planned_entry) / atr_t
                room_R = (next_opp.price - planned_entry) / planned_risk

            # ---- freeze features
            features = feat_mod.freeze_at(df, t)
            features.update({
                "was_breakout_at_tm1": bool(was_breakout),
                "broken_level_price": float(broken_level_price) if np.isfinite(broken_level_price) else None,
                "level_type": level_type,
                "level_formed_at": level_formed_at.isoformat() if isinstance(level_formed_at, pd.Timestamp) else None,
                "level_provenance": level_provenance,
                "breakout_age_bars": int(breakout_age) if breakout_age is not None else None,
                "distance_to_level_atr": float(distance_to_level_atr) if np.isfinite(distance_to_level_atr) else None,
                "holding_above_at_t": bool(holding_above),
                "room_to_next_level_atr": float(room_atr) if np.isfinite(room_atr) else None,
                "room_to_next_level_R": float(room_R) if np.isfinite(room_R) else None,
                "entry_gap_flag": gap_flag,
                "planned_entry": planned_entry,
                "planned_stop": planned_stop,
                "planned_target": planned_target,
                "actual_entry_open": actual_entry_open,
            })

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


def _validate_ohlc_columns(df: pd.DataFrame) -> None:
    required = {"open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"df missing OHLC columns: {sorted(missing)}")
