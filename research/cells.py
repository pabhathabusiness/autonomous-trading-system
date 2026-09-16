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

from dataclasses import dataclass, field
from typing import Callable, Optional


Predicate = Callable[[dict], bool]


@dataclass(frozen=True)
class Cell:
    name: str
    predicate: Predicate
    parent: Optional[str] = None
    # v0.3: `redundant_by_construction=True` marks cells that combine members
    # of the same correlated feature family (see PREREGISTRATION "Correlated
    # feature families"). Report renders them but excludes them from the
    # orthogonal-modifier lift table.
    redundant_by_construction: bool = False
    # Names of correlated feature families that this cell touches. Used by
    # the report to warn when two cells in the same family are compared as
    # if independent.
    families: tuple[str, ...] = field(default_factory=tuple)


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

# ---------------------- v0.3 context-layer orthogonal cells (B14–B26) ----
def _num_ge(key: str, th: float) -> Predicate:
    def _p(f: dict) -> bool:
        v = f.get(key)
        return v is not None and float(v) >= th
    return _p


def _num_le(key: str, th: float) -> Predicate:
    def _p(f: dict) -> bool:
        v = f.get(key)
        return v is not None and float(v) <= th
    return _p


def _eq(key: str, target) -> Predicate:
    def _p(f: dict) -> bool:
        return f.get(key) == target
    return _p


def _true(key: str) -> Predicate:
    def _p(f: dict) -> bool:
        v = f.get(key)
        return v is True
    return _p


def _b14_near_demand(f: dict) -> bool:
    if not is_inside_day(f):
        return False
    inside = f.get("supply_demand.inside_demand_zone") is True
    near = f.get("supply_demand.nearest_demand_distance_atr")
    return inside or (near is not None and abs(near) <= 0.5)


_B_ORTH_V03 = [
    Cell("B14_near_demand", _b14_near_demand,
         parent="A1_generic_inside_day",
         families=("supply_demand",)),
    Cell("B15_room_to_supply_R_ge_2",
         lambda f: is_inside_day(f) and _num_ge("supply_demand.room_to_supply_R", 2.0)(f),
         parent="A1_generic_inside_day",
         families=("zone_derived_room",)),
    Cell("B16_room_to_supply_R_ge_3",
         lambda f: is_inside_day(f) and _num_ge("supply_demand.room_to_supply_R", 3.0)(f),
         parent="A1_generic_inside_day",
         families=("zone_derived_room",)),
    Cell("B17_spy_outperforming",
         lambda f: is_inside_day(f) and _eq("relative_strength.rs_class", "OUTPERFORMING")(f),
         parent="A1_generic_inside_day",
         families=("rs_trajectory",)),
    Cell("B18_spy_trend_up",
         lambda f: is_inside_day(f) and f.get("market.spy_trend_component") in ("UPTREND", "STRONG_UPTREND"),
         parent="A1_generic_inside_day",
         families=("market_regime",)),
    Cell("B19_positive_rs_during_spy_weakness",
         lambda f: is_inside_day(f) and _num_ge("relative_strength.rs_during_spy_weakness_frac_outperformed", 0.6)(f),
         parent="A1_generic_inside_day",
         families=("rs_trajectory",)),
    Cell("B20_price_above_rising_sma50",
         lambda f: is_inside_day(f)
                   and f.get("trend.stock_above_sma50") is True
                   and f.get("trend.stock_sma_50_slope_class") == "RISING",
         parent="A1_generic_inside_day",
         families=("sma_vs_price", "sma_slope")),
    Cell("B21_bullish_sma_stack",
         lambda f: is_inside_day(f) and f.get("trend.stock_bullish_full_stack") is True,
         parent="A1_generic_inside_day",
         families=("sma_stack",)),
    Cell("B22_recent_sma50_reclaim",
         lambda f: is_inside_day(f)
                   and (f.get("trend.stock_bars_since_reclaim_sma50") is not None
                        and 0 <= f["trend.stock_bars_since_reclaim_sma50"] <= 10),
         parent="A1_generic_inside_day",
         families=("sma_events",)),
    Cell("B23_macd_bullish_expanding",
         lambda f: is_inside_day(f) and _eq("momentum.macd_state", "BULLISH_EXPANDING")(f),
         parent="A1_generic_inside_day",
         families=("macd",)),
    Cell("B24_ttm_bullish_release",
         lambda f: is_inside_day(f)
                   and (f.get("compression_volatility.bars_since_squeeze_release") is not None
                        and f["compression_volatility.bars_since_squeeze_release"] <= 5)
                   and f.get("compression_volatility.squeeze_release_direction") == "up",
         parent="A1_generic_inside_day",
         families=("vol_compression",)),
    Cell("B25_bb_expansion",
         lambda f: is_inside_day(f) and _eq("compression_volatility.bb_state", "EXPANSION")(f),
         parent="A1_generic_inside_day",
         families=("vol_compression",)),
    Cell("B26_bb_compression",
         lambda f: is_inside_day(f) and _eq("compression_volatility.bb_state", "COMPRESSION")(f),
         parent="A1_generic_inside_day",
         families=("vol_compression",)),
]


# ---------------------- v0.3 interaction cells (I1–I4) — frozen list ------
_I_INTERACTIONS = [
    # I1: SPY trend up AND stock outperforming.
    # Different families (market_regime, rs_trajectory) — NOT redundant.
    Cell("I1_spy_trend_up_AND_stock_outperforming",
         lambda f: (is_inside_day(f)
                    and f.get("market.spy_trend_component") in ("UPTREND", "STRONG_UPTREND")
                    and _eq("relative_strength.rs_class", "OUTPERFORMING")(f)),
         parent="A1_generic_inside_day",
         families=("market_regime", "rs_trajectory")),
    # I2: stock SMA50 rising while SPY SMA50 flat/falling.
    Cell("I2_stock_sma50_rising_AND_spy_sma50_flat_or_falling",
         lambda f: (is_inside_day(f)
                    and f.get("trend.stock_sma_50_slope_class") == "RISING"
                    and f.get("trend.spy_sma_50_slope_class") in ("FLAT", "FALLING")),
         parent="A1_generic_inside_day",
         families=("sma_slope",)),
    # I3: room to supply ≥ 2R AND MACD BULLISH_EXPANDING. Different families.
    Cell("I3_room_to_supply_R_ge_2_AND_positive_momentum",
         lambda f: (is_inside_day(f)
                    and _num_ge("supply_demand.room_to_supply_R", 2.0)(f)
                    and _eq("momentum.macd_state", "BULLISH_EXPANDING")(f)),
         parent="A1_generic_inside_day",
         families=("zone_derived_room", "macd")),
    # I4: TTM release AND BB expansion — SAME family (vol_compression).
    # Marked redundant_by_construction per preregistration.
    Cell("I4_ttm_release_AND_bb_expansion",
         lambda f: (is_inside_day(f)
                    and (f.get("compression_volatility.bars_since_squeeze_release") is not None
                         and f["compression_volatility.bars_since_squeeze_release"] <= 5)
                    and _eq("compression_volatility.bb_state", "EXPANSION")(f)),
         parent="A1_generic_inside_day",
         families=("vol_compression",),
         redundant_by_construction=True),
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

BIDC_CELLS: list[Cell] = [_A_BASE, *_B_ORTH, *_B_ORTH_V03, *_I_INTERACTIONS, *_C_CASCADE]

CELLS_BY_DETECTOR: dict[str, list[Cell]] = {
    "BREAKOUT_INSIDE_DAY_CONTINUATION": BIDC_CELLS,
}
