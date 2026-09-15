"""Cell definitions per detector.

A cell = (name, predicate, parent). Predicate is a plain function on a frozen
features dict → bool. Cells are FILTERS, not scores; each cell's stats are
computed from the subset of occurrences whose features satisfy the predicate.

Lift is reported as (this_cell.primary_+2R_pct − parent_cell.primary_+2R_pct)
with a ⚠ stamp when either has n_scoreable < 30.

**Orthogonal design (v0.2)**: for each detector, we ship three cell groups:
  A. BASE  — control
  B. Orthogonal single modifiers, each parent=BASE — every modifier is
     testable on its own without being buried in a nested cascade.
  C. Cascade — the nested chain, kept because it was explicitly requested.
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


# ------------------------------- reusable modifier predicates
def has_compression(f: dict) -> bool:
    return bool(f.get("compression", False))


def has_fresh_reaccel_up(f: dict) -> bool:
    return bool(f.get("fresh_macd_reaccel_up", False))


def has_fresh_reaccel_down(f: dict) -> bool:
    return bool(f.get("fresh_macd_reaccel_down", False))


def has_ema_stack_up(f: dict) -> bool:
    return bool(f.get("ema_stack_up", False))


def has_ema_stack_down(f: dict) -> bool:
    return bool(f.get("ema_stack_down", False))


def room_up_ge_2R(f: dict) -> bool:
    r = f.get("room_to_next_level_R")
    return bool(r is not None and r >= 2.0)


def is_gap_clean(f: dict) -> bool:
    return f.get("entry_gap_flag") == "clean"


def is_inside_day(f: dict) -> bool:
    return bool(f.get("inside_day", False))


def was_breakout(f: dict) -> bool:
    return bool(f.get("was_breakout_at_tm1", False))


def holding_above(f: dict) -> bool:
    return bool(f.get("holding_above_at_t", False))


def level_type_is(target: str) -> Predicate:
    def _p(f: dict) -> bool:
        return f.get("level_type") == target
    return _p


def level_type_in(targets: tuple[str, ...]) -> Predicate:
    def _p(f: dict) -> bool:
        return f.get("level_type") in targets
    return _p


def breakout_age_eq(n: int) -> Predicate:
    def _p(f: dict) -> bool:
        return f.get("breakout_age_bars") == n
    return _p


def breakout_age_between(lo: int, hi: int) -> Predicate:
    def _p(f: dict) -> bool:
        a = f.get("breakout_age_bars")
        return a is not None and lo <= a <= hi
    return _p


def breakout_age_ge(n: int) -> Predicate:
    def _p(f: dict) -> bool:
        a = f.get("breakout_age_bars")
        return a is not None and a >= n
    return _p


# ================================================================= BIDC
# Group A — BASE (control)
_A_BASE = Cell("A1_generic_inside_day", is_inside_day, parent=None)

# Group B — orthogonal single modifiers (parent = A1)
_B_ORTH = [
    Cell("B1_ema_stack_up",
         lambda f: is_inside_day(f) and has_ema_stack_up(f),
         parent="A1_generic_inside_day"),
    Cell("B2_after_breakout_any_level",
         lambda f: is_inside_day(f) and was_breakout(f),
         parent="A1_generic_inside_day"),
    Cell("B3_holding_above",
         lambda f: is_inside_day(f) and was_breakout(f) and holding_above(f),
         parent="A1_generic_inside_day"),
    Cell("B4_compression",
         lambda f: is_inside_day(f) and has_compression(f),
         parent="A1_generic_inside_day"),
    Cell("B5_fresh_macd_reaccel_up",
         lambda f: is_inside_day(f) and has_fresh_reaccel_up(f),
         parent="A1_generic_inside_day"),
    Cell("B6_room_to_next_level_ge_2R",
         lambda f: is_inside_day(f) and room_up_ge_2R(f),
         parent="A1_generic_inside_day"),
    Cell("B7_level_type_swing_pivot",
         lambda f: is_inside_day(f) and was_breakout(f) and level_type_is("swing_pivot")(f),
         parent="A1_generic_inside_day"),
    Cell("B8_level_type_horizontal_resistance",
         lambda f: is_inside_day(f) and was_breakout(f) and level_type_is("horizontal_resistance")(f),
         parent="A1_generic_inside_day"),
    Cell("B9_level_type_known_level",
         lambda f: is_inside_day(f) and was_breakout(f)
                   and level_type_in(("round_number", "prior_day_high",
                                       "prior_week_high", "prior_month_high"))(f),
         parent="A1_generic_inside_day"),
    Cell("B10_breakout_age_0",
         lambda f: is_inside_day(f) and breakout_age_eq(0)(f),
         parent="A1_generic_inside_day"),
    Cell("B11_breakout_age_1_to_2",
         lambda f: is_inside_day(f) and breakout_age_between(1, 2)(f),
         parent="A1_generic_inside_day"),
    Cell("B12_breakout_age_3plus",
         lambda f: is_inside_day(f) and breakout_age_ge(3)(f),
         parent="A1_generic_inside_day"),
    Cell("B13_gap_clean",
         lambda f: is_inside_day(f) and is_gap_clean(f),
         parent="A1_generic_inside_day"),
]

# Group C — cascade (nested, retained per original spec)
_C_CASCADE = [
    Cell("C1_cascade_after_breakout",
         lambda f: is_inside_day(f) and was_breakout(f),
         parent="A1_generic_inside_day"),
    Cell("C2_cascade_holding_above",
         lambda f: is_inside_day(f) and was_breakout(f) and holding_above(f),
         parent="C1_cascade_after_breakout"),
    Cell("C3_cascade_holding_plus_compression",
         lambda f: is_inside_day(f) and was_breakout(f) and holding_above(f) and has_compression(f),
         parent="C2_cascade_holding_above"),
    Cell("C4_cascade_holding_plus_fresh_macd",
         lambda f: is_inside_day(f) and was_breakout(f) and holding_above(f) and has_fresh_reaccel_up(f),
         parent="C2_cascade_holding_above"),
    Cell("C5_cascade_holding_plus_both",
         lambda f: (is_inside_day(f) and was_breakout(f) and holding_above(f)
                    and has_compression(f) and has_fresh_reaccel_up(f)),
         parent="C2_cascade_holding_above"),
]

BIDC_CELLS: list[Cell] = [_A_BASE, *_B_ORTH, *_C_CASCADE]

CELLS_BY_DETECTOR: dict[str, list[Cell]] = {
    "BREAKOUT_INSIDE_DAY_CONTINUATION": BIDC_CELLS,
}
