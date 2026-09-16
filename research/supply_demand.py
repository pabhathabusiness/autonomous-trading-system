"""Supply / demand zones — causal, deterministic, auditable.

v0.3.0 first pass uses the "base + impulse" rule preregistered in
PREREGISTRATION.md § 1. Every zone carries provenance:
`created_at`, `known_at_bar`, `source_bar`, `source_reason`. Nothing here
uses future bars to establish an earlier zone.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from typing import Literal

import numpy as np
import pandas as pd

from . import math_utils as mu


ZoneType = Literal["demand", "supply"]


@dataclass(frozen=True)
class Zone:
    zone_id: str
    zone_type: ZoneType
    price_low: float
    price_high: float
    midpoint: float
    source_bar: pd.Timestamp
    known_at_bar: pd.Timestamp
    created_at: pd.Timestamp
    source_reason: str
    departure_atr: float
    departure_pct: float
    width_atr: float
    # Dynamic fields — recomputed at query time via evaluate_at()
    active: bool = True
    invalidated_at: pd.Timestamp | None = None
    age_bars: int = 0
    touches_since_creation: int = 0
    freshness: float = 1.0


def _hash_id(symbol: str, ts: pd.Timestamp, ztype: str) -> str:
    h = hashlib.sha256(f"{symbol}|{ts.isoformat()}|{ztype}".encode()).hexdigest()
    return h[:16]


def _find_base_before(df: pd.DataFrame, impulse_idx: int, atr_at_impulse: float,
                     min_bars: int = 2, max_bars: int = 4,
                     range_atr_cap: float = 0.7) -> tuple[int, int] | None:
    """Find a base of `min_bars..max_bars` consecutive bars immediately before
    `impulse_idx`, each with range ≤ `range_atr_cap · ATR14_at_impulse`.

    Returns (base_start_iloc, base_end_iloc) inclusive, or None."""
    if impulse_idx < min_bars:
        return None
    end = impulse_idx - 1
    # Extend base as far back as it holds, up to max_bars
    for n in range(max_bars, min_bars - 1, -1):
        start = end - n + 1
        if start < 0:
            continue
        window = df.iloc[start:end + 1]
        ranges = (window["high"] - window["low"]).to_numpy()
        if np.all(ranges <= range_atr_cap * atr_at_impulse):
            return (start, end)
    return None


def detect_zones(symbol: str, df: pd.DataFrame,
                *, atr_period: int = 14,
                impulse_close_open_atr: float = 1.5,
                impulse_base_min: int = 2,
                impulse_base_max: int = 4,
                base_range_atr_cap: float = 0.7) -> list[Zone]:
    """Scan `df` end-to-end and emit zones. Only OHLC is consulted; each zone's
    `known_at_bar` is the impulse bar's index — the earliest bar at which the
    zone is observable. Purely causal.

    The output is a chronological list. Dynamic fields (`age_bars`,
    `touches_since_creation`, `active`, `invalidated_at`, `freshness`) are
    left at their initial values; call `evaluate_at(zones, df, t)` to
    project them onto a specific evaluation bar t.
    """
    _validate_ohlc(df)
    if len(df) < atr_period + impulse_base_max + 1:
        return []

    atr = mu.atr(df, atr_period)
    zones: list[Zone] = []

    for i in range(atr_period + impulse_base_max, len(df)):
        atr_i = float(atr.iloc[i]) if pd.notna(atr.iloc[i]) else float("nan")
        if not np.isfinite(atr_i) or atr_i <= 0:
            continue

        open_i = float(df.iloc[i]["open"])
        close_i = float(df.iloc[i]["close"])
        high_i = float(df.iloc[i]["high"])
        low_i = float(df.iloc[i]["low"])
        prev_high = float(df.iloc[i - 1]["high"])
        prev_low = float(df.iloc[i - 1]["low"])

        body = close_i - open_i
        # Impulse up
        if body >= impulse_close_open_atr * atr_i and close_i > prev_high:
            base = _find_base_before(df, i, atr_i,
                                     min_bars=impulse_base_min,
                                     max_bars=impulse_base_max,
                                     range_atr_cap=base_range_atr_cap)
            if base is None:
                continue
            base_start, base_end = base
            plo = float(df.iloc[base_start:base_end + 1]["low"].min())
            phi = float(df.iloc[base_start:base_end + 1]["high"].max())
            zid = _hash_id(symbol, df.index[i], "demand")
            zones.append(Zone(
                zone_id=zid,
                zone_type="demand",
                price_low=plo, price_high=phi, midpoint=(plo + phi) / 2,
                source_bar=df.index[i],
                known_at_bar=df.index[i],
                created_at=df.index[base_start],
                source_reason="base_impulse",
                departure_atr=(high_i - low_i) / atr_i,
                departure_pct=body / open_i if open_i > 0 else 0.0,
                width_atr=(phi - plo) / atr_i,
            ))
            continue

        # Impulse down (symmetric)
        if body <= -impulse_close_open_atr * atr_i and close_i < prev_low:
            base = _find_base_before(df, i, atr_i,
                                     min_bars=impulse_base_min,
                                     max_bars=impulse_base_max,
                                     range_atr_cap=base_range_atr_cap)
            if base is None:
                continue
            base_start, base_end = base
            plo = float(df.iloc[base_start:base_end + 1]["low"].min())
            phi = float(df.iloc[base_start:base_end + 1]["high"].max())
            zid = _hash_id(symbol, df.index[i], "supply")
            zones.append(Zone(
                zone_id=zid,
                zone_type="supply",
                price_low=plo, price_high=phi, midpoint=(plo + phi) / 2,
                source_bar=df.index[i],
                known_at_bar=df.index[i],
                created_at=df.index[base_start],
                source_reason="base_impulse",
                departure_atr=(high_i - low_i) / atr_i,
                departure_pct=abs(body) / open_i if open_i > 0 else 0.0,
                width_atr=(phi - plo) / atr_i,
            ))
    return zones


def evaluate_at(zones: list[Zone], df: pd.DataFrame, t: int,
                *, atr_period: int = 14, invalidation_pad_atr: float = 0.1) -> list[Zone]:
    """Project each zone's dynamic fields (active/invalidated_at/age/touches/
    freshness) onto evaluation bar `t`. Only bars ≤ t are consulted — a zone
    invalidated by a bar > t remains active.

    Returns a NEW list of Zone objects (immutability of the input preserved).
    """
    if t < 0 or t >= len(df):
        raise IndexError(f"t={t} out of range for df of length {len(df)}")
    atr = mu.atr(df, atr_period)
    out: list[Zone] = []
    for z in zones:
        try:
            k_iloc = df.index.get_loc(z.known_at_bar)
        except KeyError:
            out.append(z)
            continue
        if k_iloc > t:
            out.append(z)  # not yet known at t
            continue

        # Age
        age = t - k_iloc

        # Invalidation: first bar after known_at with close beyond the far side
        atr_at_known = float(atr.iloc[k_iloc]) if pd.notna(atr.iloc[k_iloc]) else 0.0
        pad = invalidation_pad_atr * atr_at_known
        window = df.iloc[k_iloc + 1: t + 1]
        invalidated_at: pd.Timestamp | None = None
        if z.zone_type == "demand":
            below = window[window["close"] < (z.price_low - pad)]
            if not below.empty:
                invalidated_at = below.index[0]
        else:
            above = window[window["close"] > (z.price_high + pad)]
            if not above.empty:
                invalidated_at = above.index[0]

        # Touches (bars where price re-entered the zone range)
        touches = 0
        eff_end = t if invalidated_at is None else df.index.get_loc(invalidated_at)
        touch_window = df.iloc[k_iloc + 1: eff_end + 1]
        if not touch_window.empty:
            touched = (touch_window["low"] <= z.price_high) & (touch_window["high"] >= z.price_low)
            touches = int(touched.sum())

        freshness = max(0.0, 1.0 - 0.2 * touches)
        active = invalidated_at is None

        out.append(Zone(
            zone_id=z.zone_id, zone_type=z.zone_type,
            price_low=z.price_low, price_high=z.price_high, midpoint=z.midpoint,
            source_bar=z.source_bar, known_at_bar=z.known_at_bar,
            created_at=z.created_at, source_reason=z.source_reason,
            departure_atr=z.departure_atr, departure_pct=z.departure_pct,
            width_atr=z.width_atr,
            active=active, invalidated_at=invalidated_at, age_bars=age,
            touches_since_creation=touches, freshness=freshness,
        ))
    return out


def context_at(zones: list[Zone], df: pd.DataFrame, t: int,
               planned_risk_unit: float, *,
               atr_period: int = 14) -> dict:
    """Compute per-occurrence supply/demand context at bar t. Consults only
    bars ≤ t. Requires `planned_risk_unit` (frozen at signal time — never
    a future-adjusted value)."""
    if t < 0 or t >= len(df):
        raise IndexError(f"t={t} out of range for df of length {len(df)}")
    atr = mu.atr(df, atr_period)
    atr_t = float(atr.iloc[t]) if pd.notna(atr.iloc[t]) else float("nan")
    price = float(df.iloc[t]["close"])

    evaluated = evaluate_at(zones, df, t, atr_period=atr_period)
    active = [z for z in evaluated if z.active and df.index.get_loc(z.known_at_bar) <= t]
    demand = [z for z in active if z.zone_type == "demand"]
    supply = [z for z in active if z.zone_type == "supply"]

    def _nearest_dist(zs: list[Zone]) -> tuple[Zone | None, float]:
        """Nearest zone by min |price − midpoint|; returns (zone, atr-normalized signed dist)."""
        if not zs:
            return None, float("nan")
        best = min(zs, key=lambda z: abs(price - z.midpoint))
        d_atr = ((best.midpoint - price) / atr_t) if np.isfinite(atr_t) and atr_t > 0 else float("nan")
        return best, d_atr

    dz, d_atr = _nearest_dist(demand)
    sz, s_atr = _nearest_dist(supply)

    inside_demand = any(z.price_low <= price <= z.price_high for z in demand)
    inside_supply = any(z.price_low <= price <= z.price_high for z in supply)

    # Room to opposing structure (supply above price for longs; demand below for shorts)
    supply_above = [z for z in supply if z.price_low > price]
    demand_below = [z for z in demand if z.price_high < price]

    def _room_to(zs: list[Zone], direction: str) -> tuple[float, float]:
        """Return (room_atr, room_R) for the nearest zone in `direction`
        (up | down). NaN if none."""
        if not zs:
            return float("nan"), float("nan")
        if direction == "up":
            zone = min(zs, key=lambda z: z.price_low)
            edge = zone.price_low
            room_price = edge - price
        else:
            zone = max(zs, key=lambda z: z.price_high)
            edge = zone.price_high
            room_price = price - edge
        room_atr = room_price / atr_t if np.isfinite(atr_t) and atr_t > 0 else float("nan")
        room_R = room_price / planned_risk_unit if planned_risk_unit > 0 else float("nan")
        return room_atr, room_R

    room_supply_atr, room_supply_R = _room_to(supply_above, "up")
    room_demand_atr, room_demand_R = _room_to(demand_below, "down")

    return {
        "supply_demand.nearest_demand_distance_atr": float(d_atr) if np.isfinite(d_atr) else None,
        "supply_demand.nearest_supply_distance_atr": float(s_atr) if np.isfinite(s_atr) else None,
        "supply_demand.inside_demand_zone": bool(inside_demand),
        "supply_demand.inside_supply_zone": bool(inside_supply),
        "supply_demand.demand_zone_freshness": (dz.freshness if dz else None),
        "supply_demand.supply_zone_freshness": (sz.freshness if sz else None),
        "supply_demand.demand_zone_age_bars": (dz.age_bars if dz else None),
        "supply_demand.supply_zone_age_bars": (sz.age_bars if sz else None),
        "supply_demand.room_to_supply_atr": float(room_supply_atr) if np.isfinite(room_supply_atr) else None,
        "supply_demand.room_to_demand_atr": float(room_demand_atr) if np.isfinite(room_demand_atr) else None,
        "supply_demand.room_to_supply_R": float(room_supply_R) if np.isfinite(room_supply_R) else None,
        "supply_demand.room_to_demand_R": float(room_demand_R) if np.isfinite(room_demand_R) else None,
        "supply_demand._feature_version": "v0.3.0",
        "supply_demand._n_active_demand": len(demand),
        "supply_demand._n_active_supply": len(supply),
    }


def _validate_ohlc(df: pd.DataFrame) -> None:
    required = {"open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"df missing OHLC columns: {sorted(missing)}")
