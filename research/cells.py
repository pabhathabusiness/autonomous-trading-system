"""Cell definitions.

A cell is (name, predicate, parent_name_or_None). The predicate is a plain
function on a frozen features dict → bool. Cells are NOT scores; they are
FILTERS. Each cell's stats are computed from the subset of occurrences whose
features satisfy the predicate.

Lift is reported as (this_cell.win_rate − parent_cell.win_rate) with warning
when either has n < 30.

Every detector defines its own cell list. Standard modifier cells (key level,
compression, momentum transition, structural trigger, available space) are
provided as reusable predicates for the other detectors.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


Predicate = Callable[[dict], bool]


@dataclass(frozen=True)
class Cell:
    name: str
    predicate: Predicate
    parent: Optional[str] = None


# ------------------------------- standard modifier predicates (reusable)
def has_compression(f: dict) -> bool:
    return bool(f.get("compression", False))


def has_fresh_momentum_up(f: dict) -> bool:
    return f.get("macd_state") in ("cross_up", "accel_up")


def has_fresh_momentum_down(f: dict) -> bool:
    return f.get("macd_state") in ("cross_down", "accel_down")


def has_fresh_reaccel_up(f: dict) -> bool:
    return bool(f.get("fresh_macd_reaccel_up", False))


def has_ema_stack_up(f: dict) -> bool:
    return bool(f.get("ema_stack_up", False))


def has_ema_stack_down(f: dict) -> bool:
    return bool(f.get("ema_stack_down", False))


def key_level_above_close(f: dict, atr_mult: float = 0.5) -> bool:
    p = f.get("pivot_above")
    price = f.get("price_t")
    atr14 = f.get("atr14")
    if p is None or price is None or atr14 is None or atr14 <= 0:
        return False
    return abs(p - price) <= atr_mult * atr14


def room_up_available(f: dict, mult: float = 2.0) -> bool:
    r = f.get("room_above_atr")
    return bool(r is not None and r >= mult)


# ------------------------------- BREAKOUT_INSIDE_DAY_CONTINUATION cells

def _always(f: dict) -> bool:
    return True


def _was_breakout(f: dict) -> bool:
    return bool(f.get("was_breakout_at_tm1", False))


def _holding_above(f: dict) -> bool:
    return bool(f.get("holding_above_at_t", False))


BIDC_CELLS: list[Cell] = [
    Cell("generic_inside_day", _always, parent=None),  # control
    Cell("inside_day_uptrend",
         lambda f: _always(f) and has_ema_stack_up(f),
         parent="generic_inside_day"),
    Cell("inside_day_after_breakout",
         _was_breakout,
         parent="generic_inside_day"),
    Cell("inside_day_after_breakout_holding_above",
         lambda f: _was_breakout(f) and _holding_above(f),
         parent="inside_day_after_breakout"),
    Cell("holding_above_plus_compression",
         lambda f: _was_breakout(f) and _holding_above(f) and has_compression(f),
         parent="inside_day_after_breakout_holding_above"),
    Cell("holding_above_plus_fresh_macd_reaccel",
         lambda f: _was_breakout(f) and _holding_above(f) and has_fresh_reaccel_up(f),
         parent="inside_day_after_breakout_holding_above"),
    Cell("holding_above_plus_both",
         lambda f: (_was_breakout(f) and _holding_above(f)
                    and has_compression(f) and has_fresh_reaccel_up(f)),
         parent="inside_day_after_breakout_holding_above"),
]


CELLS_BY_DETECTOR: dict[str, list[Cell]] = {
    "BREAKOUT_INSIDE_DAY_CONTINUATION": BIDC_CELLS,
    # Others added when detectors land.
}
