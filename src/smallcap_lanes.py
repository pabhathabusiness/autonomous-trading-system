"""
Small-cap lane engine — FINAL SIX theses (no more drift).

  reversal · breakout · compression · emerging_strength · hidden_value · turnaround

Renamed from the old set (bounce->reversal, coiled->compression, value->
hidden_value); runner/hailmary/special DELETED (lottery/intraday lanes the trader
profile rejects; the good parts fold into breakout + emerging_strength). breakout
is NET-NEW (specced in Addendum 2 as "Scan B", lost in the A3 rewrite).

Scoring: 9 weighted edge families -> 0-10 composite; a trigger needs
`composite >= THRESHOLD AND >= 3 independent families >= 0.5`.

BUG-5 FIX (the empty-page cause): the composite normalizes over the AVAILABLE
families only. A family whose DATA does not exist (no fundamentals, no news in
window, no insider filings) is EXCLUDED from both numerator and denominator --
it no longer lowers the ceiling. A family whose data EXISTS but reads zero stays
in the denominator (correctly penalizing). That distinction was the bug.
"""

from __future__ import annotations

from typing import Any, Optional

LANES = ("reversal", "breakout", "compression", "emerging_strength", "hidden_value", "turnaround")
THESIS = {
    "reversal": "Oversold at a real demand zone — sellers exhausted, buyers stepping in.",
    "breakout": "A quiet base expanding out on volume — the retest is the best entry.",
    "compression": "A squeeze coiled tight — direction unknown until it fires.",
    "emerging_strength": "Early in a move with a sector tailwind, before it's obvious.",
    "hidden_value": "Cheap, real, and uncovered — a business the tape hasn't noticed.",
    "turnaround": "A fundamental inflection forming before the re-rating.",
}
EDGE_FAMILIES = ("volume", "structure", "compression", "trend", "fundamental",
                 "catalyst", "sector", "float", "insider")

COMPOSITE_THRESHOLD = 6.5    # provisional (weekday re-validation owed)
MIN_FAMILIES = 3
FAMILY_FIRE = 0.5

# FLOODGATE GUARD (adversarial-review finding). BUG-5's available-only denominator
# re-normalizes onto whatever families have data. For chart-driven lanes that just
# un-empties the page (multiplier ~1.0). But for the fundamental-thesis lanes it
# lets the denominator COLLAPSE onto OHLC families when the thesis families are
# absent (the normal small-cap case) -> a 2x lift that fires the lane on pure chart
# data with zero evidence for the thesis. Two guards close it:
#   (1) MIN_COVERAGE: a lane may not judge itself when > half its edge WEIGHT is
#       absent -- the surviving families can't carry the thesis.
#   (2) require_available (per lane, below): a fundamental-thesis lane must have its
#       core family's DATA present to fire at all.
MIN_COVERAGE = 0.55

# migration map old lane value -> new (used by the DB migration + readers)
LANE_REMAP = {"bounce": "reversal", "coiled": "compression", "value": "hidden_value"}
LANE_DELETED = {"runner", "hailmary", "special"}   # -> legacy_<old>

# GATE 2: a lane whose THESIS-CORE family is degraded is DISABLED -- an honest
# empty tab beats a lane confidently mislabeling setups. A family is a lane's
# thesis-core when the lane's whole premise depends on SEEING it: insider
# accumulation + catalyst for turnaround; insider confirmation for hidden_value.
# The chart-driven lanes have no degradable core (their families are ~always
# fetched), so they are never auto-disabled.
THESIS_CORE = {
    "turnaround": ("insider", "catalyst"),
    "hidden_value": ("insider",),
}
DEGRADE_THRESHOLD = 0.90

_WEIGHTS = {
    "reversal":          {"volume": 2.0, "structure": 3.0, "compression": 1.0, "trend": 0.0, "fundamental": 0.5, "catalyst": 1.5, "sector": 1.0, "float": 1.0, "insider": 1.5},
    "breakout":          {"volume": 3.0, "structure": 3.0, "compression": 1.5, "trend": 2.0, "fundamental": 0.0, "catalyst": 1.5, "sector": 1.5, "float": 0.5, "insider": 0.0},
    "compression":       {"volume": 1.5, "structure": 1.5, "compression": 3.5, "trend": 0.5, "fundamental": 0.0, "catalyst": 1.0, "sector": 1.0, "float": 1.0, "insider": 0.5},
    "emerging_strength": {"volume": 2.0, "structure": 1.5, "compression": 0.5, "trend": 3.0, "fundamental": 0.5, "catalyst": 1.0, "sector": 2.5, "float": 0.5, "insider": 0.5},
    "hidden_value":      {"volume": 0.5, "structure": 1.0, "compression": 1.0, "trend": 2.0, "fundamental": 3.5, "catalyst": 0.5, "sector": 0.5, "float": 0.0, "insider": 2.5},
    "turnaround":        {"volume": 0.5, "structure": 1.0, "compression": 0.5, "trend": 1.5, "fundamental": 3.0, "catalyst": 2.0, "sector": 0.5, "float": 0.5, "insider": 2.5},
}
_LANE_META = {
    "reversal":          {"float_ceiling": 500, "price_tiers": ("special", "low", "sub2"), "bands": ("short", "medium"),    "hard": (), "gate": "reversal"},
    "breakout":          {"float_ceiling": 500, "price_tiers": ("special", "low", "sub2"), "bands": ("short", "medium"),    "hard": (), "gate": "breakout"},
    "compression":       {"float_ceiling": 300, "price_tiers": ("special", "low", "sub2"), "bands": ("short", "medium"),    "hard": (), "gate": None},
    "emerging_strength": {"float_ceiling": 500, "price_tiers": ("special", "low", "sub2"), "bands": ("medium", "position"), "hard": (), "gate": None},
    "hidden_value":      {"float_ceiling": 500, "price_tiers": ("special", "low"),         "bands": ("medium", "position"), "hard": (), "gate": None, "require_available": ("fundamental", "insider")},
    "turnaround":        {"float_ceiling": 500, "price_tiers": ("special", "low"),         "bands": ("position", "medium"), "hard": (), "gate": None, "require_available": ("fundamental", "insider", "catalyst")},
}
_BANDS = {  # band -> (rr_floor, time_stop_days, atr_stop_mult, atr_target_mult)
    "overnight": (1.8, 2, 0.6, 1.5), "short": (2.0, 5, 1.0, 2.0),
    "medium": (2.2, 15, 1.5, 3.0), "position": (2.2, 40, 2.0, 4.0),
}


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# ---------------------------------------------------------------- edge families
def _fam_volume(row, sig, dt) -> float:
    rv = row.get("rel_vol") or 0
    score = _clamp((rv - 1.0) / 2.0)
    if dt.get("exhaustion"):
        score = max(score, 0.6)
    return _clamp(score)


def _fam_structure(row, sig, dt) -> float:
    s = 0.0
    if dt.get("at_real_level"):
        s += 0.4 * (dt.get("level_quality") or 0.6)
    if dt.get("undercut_reclaim"):
        s += 0.3
    if dt.get("reclaim_prior_high"):
        s += 0.3
    if dt.get("above_sma20"):
        s += 0.15
    if dt.get("broke_out") or dt.get("retest"):
        s += 0.4
    if dt.get("weekly_breakout"):
        s += 0.5
    if dt.get("weekly_base") and dt.get("weekly_higher_lows"):
        s += 0.4
    return _clamp(s)


def _fam_compression(row, sig, dt) -> float:
    if row.get("compression_extreme"):
        return 1.0
    bb = row.get("bb_percentile")
    if bb is None:
        return 0.0
    base = _clamp((20.0 - bb) / 20.0)
    if (row.get("squeeze_days") or 0) >= 5:
        base = max(base, 0.6)
    return _clamp(base)


def _fam_trend(row, sig, dt) -> float:
    s = (0.25 * bool(dt.get("above_sma20")) + 0.25 * bool(dt.get("above_sma50"))
         + 0.25 * bool(dt.get("sma50_slope_up")) + 0.15 * bool(row.get("up_wow"))
         + 0.10 * _clamp((row.get("consecutive_up_weeks") or 0) / 8.0))
    return _clamp(s)


def _fam_fundamental(row, sig, dt) -> float:
    f = sig.get("fundamentals") or {}
    parts = []
    if f.get("revenueGrowthYoY") is not None:
        parts.append(_clamp(f["revenueGrowthYoY"] / 50.0))
    if f.get("grossMarginTTM") is not None:
        parts.append(_clamp(f["grossMarginTTM"] / 50.0))
    if f.get("debtToEquity") is not None:
        parts.append(_clamp((2.0 - f["debtToEquity"]) / 2.0))
    if f.get("operCashFlowPerShareTTM") is not None:
        parts.append(1.0 if f["operCashFlowPerShareTTM"] > 0 else 0.2)
    trend = sig.get("fundamental_trends") or {}
    if trend.get("revenue_trend") == "accelerating":
        parts.append(1.0)
    elif trend.get("revenue_trend") == "decelerating":
        parts.append(0.2)
    return round(sum(parts) / len(parts), 3) if parts else 0.0


def _fam_catalyst(row, sig, dt) -> float:
    cls = sig.get("catalyst_class")
    if cls is not None:
        return _clamp(cls.get("weight", 0.0))
    cat = sig.get("catalyst")
    if not cat:
        return 0.0
    return _clamp(0.5 + 0.5 * _clamp(1 - (cat.get("age_h") or 48) / 48.0))


def _fam_sector(row, sig, dt, sector_early: bool) -> float:
    s = 0.0
    if sector_early:
        s += 0.7
    heat = sig.get("sector_heat")
    if heat is not None:
        s += _clamp(heat / 3.0) * 0.5
    return _clamp(s if s else (0.4 if sig.get("sector_bull") else 0.0))


def _fam_float(row, sig, dt) -> float:
    fe = row.get("float_est")
    if fe is None:
        return 0.0
    if fe < 20:
        return 1.0
    if fe < 50:
        return 0.8
    if fe < 150:
        return 0.5
    if fe < 500:
        return 0.25
    return 0.1


def _fam_insider(row, sig, dt) -> float:
    return _clamp((sig.get("insider") or {}).get("score", 0.0))


def compute_families(row, *, sector_early: bool = False) -> tuple[dict[str, float], dict[str, bool]]:
    """(scores, available). `available` drives the BUG-5 denominator: a family is
    UNAVAILABLE when its underlying DATA does not exist -- distinct from a family
    whose data exists but reads zero."""
    sig = row.get("signals") or {}
    dt = sig.get("demand_trend") or {}
    f = sig.get("fundamentals") or {}
    scores = {
        "volume": _fam_volume(row, sig, dt), "structure": _fam_structure(row, sig, dt),
        "compression": _fam_compression(row, sig, dt), "trend": _fam_trend(row, sig, dt),
        "fundamental": _fam_fundamental(row, sig, dt), "catalyst": _fam_catalyst(row, sig, dt),
        "sector": _fam_sector(row, sig, dt, sector_early), "float": _fam_float(row, sig, dt),
        "insider": _fam_insider(row, sig, dt),
    }
    fund_avail = any(f.get(k) is not None for k in
                     ("revenueGrowthYoY", "grossMarginTTM", "debtToEquity", "operCashFlowPerShareTTM"))
    available = {
        "volume": row.get("rel_vol") is not None, "structure": bool(dt),
        "compression": row.get("bb_percentile") is not None, "trend": bool(dt),
        "fundamental": fund_avail,
        "catalyst": bool(sig.get("news_available")) or bool(sig.get("catalyst")),
        "sector": True,                                  # panel is a system input
        "float": row.get("float_est") is not None,
        "insider": bool((sig.get("insider") or {}).get("available", False)),
    }
    return scores, available


# ---------------------------------------------------------------- gates + penalties
def _gate_reversal(row, sig, dt) -> Optional[list[str]]:
    """Oversold at a REAL demand zone with exhaustion + >=2/3 confirmation.
    Returns the demand_signals list on pass, None on fail."""
    r52 = sig.get("pct_of_52w_range")
    if r52 is None or r52 >= 0.25:
        return None
    if not dt.get("at_real_level") or not dt.get("exhaustion"):
        return None
    ds = []
    if (row.get("rel_vol") or 0) >= 2.0 and dt.get("upper_third_close"):
        ds.append("relvol_upperthird")
    if dt.get("undercut_reclaim"):
        ds.append("undercut_reclaim")
    if dt.get("reclaim_prior_high"):
        ds.append("reclaim_prior_high")
    return ds if len(ds) >= 2 else None


def _gate_breakout(row, sig, dt) -> Optional[list[str]]:
    """base -> expansion on volume. Daily (close>base_high on rel_vol>=1.8),
    WEEKLY, or RETEST (best). Returns the variant tags on pass."""
    tags = []
    if dt.get("broke_out") and (row.get("rel_vol") or 0) >= 1.8:
        tags.append("DAILY BREAKOUT")
    if dt.get("weekly_breakout"):
        tags.append("WEEKLY BREAKOUT")
    if dt.get("retest"):
        tags.append("RETEST")
    return tags or None


_GATES = {"reversal": _gate_reversal, "breakout": _gate_breakout}


def _penalties(row: dict[str, Any]) -> tuple[float, list[str]]:
    sig = row.get("signals") or {}
    pts, chips = 0.0, []
    if sig.get("delisting_risk") and row.get("price_tier") != "deep":
        pts -= 1.5
        chips.append("DELISTING RISK")
    cw = (sig.get("catalyst_class") or {}).get("weight", 0.0) or 0.0
    if cw < 0:
        pts += cw
        chips.append("OFFERING" if (sig.get("catalyst_class") or {}).get("type") == "offering" else "NEWS NEG")
    if (sig.get("insider") or {}).get("heavy_selling"):
        pts -= 0.5
        chips.append("INSIDER SELLING")
    # A3 BUG-8: reverse split is a scored penalty + tag, not a hard exclusion
    rs = sig.get("reverse_split") or {}
    if rs.get("reverse_18mo") and not rs.get("serial_reverse"):
        pts -= 0.75
        chips.append("R-SPLIT")
    return pts, chips


def _hard_pass(row: dict[str, Any]) -> Optional[str]:
    return "going_concern" if (row.get("signals") or {}).get("going_concern") else None


def _eligible(lane: str, row: dict[str, Any]) -> bool:
    meta = _LANE_META[lane]
    fe = row.get("float_est")
    if fe is not None and fe > meta["float_ceiling"]:
        return False
    if meta["price_tiers"] and row.get("price_tier") not in meta["price_tiers"]:
        return False
    for req in meta["hard"]:
        if not row.get(req):
            return False
    return True


def _pick_band(lane: str, dt: dict[str, Any]) -> str:
    eligible = _LANE_META[lane]["bands"]
    if "medium" in eligible and (dt.get("weekly_breakout") or dt.get("weekly_base")):
        return "medium"
    return eligible[0]


def eval_lane(lane: str, row: dict[str, Any], scores: dict[str, float],
              avail: dict[str, bool], pen_pts: float, pen_chips: list[str]) -> Optional[dict[str, Any]]:
    if not _eligible(lane, row):
        return None
    sig = row.get("signals") or {}
    dt = sig.get("demand_trend") or {}
    gate_tags: list[str] = []
    if _LANE_META[lane]["gate"]:
        res = _GATES[_LANE_META[lane]["gate"]](row, sig, dt)
        if res is None:
            return None
        gate_tags = res
    # FLOODGATE GUARD (2): a fundamental-thesis lane must have its core family's DATA
    # present -- otherwise the composite is a chart score wearing a value/inflection label.
    for req in _LANE_META[lane].get("require_available", ()):
        if not avail.get(req):
            return None
    w = _WEIGHTS[lane]
    # BUG-5: normalize over AVAILABLE families only
    num = sum(w[f] * scores[f] for f in EDGE_FAMILIES if avail[f] and w[f] > 0)
    den = sum(w[f] for f in EDGE_FAMILIES if avail[f] and w[f] > 0)
    den_all = sum(w[f] for f in EDGE_FAMILIES if w[f] > 0)
    if den <= 0 or den_all <= 0:
        return None
    # FLOODGATE GUARD (1): can't judge the thesis when > half its edge weight is absent
    if den / den_all < MIN_COVERAGE:
        return None
    composite = round(_clamp(10.0 * num / den + pen_pts, 0.0, 10.0), 2)
    fired = [f for f in EDGE_FAMILIES if avail[f] and scores[f] >= FAMILY_FIRE and w[f] > 0]
    # sector is a system panel, not a name-specific signal -> it doesn't count toward
    # the "3 independent families" that establish a real setup on THIS name.
    fired_ns = [f for f in fired if f != "sector"]
    if composite < COMPOSITE_THRESHOLD or len(fired_ns) < MIN_FAMILIES:
        return None
    band = _pick_band(lane, dt)
    rr, tstop, _, _ = _BANDS[band]
    chips = list(pen_chips) + list(gate_tags)
    if row.get("compression_extreme"):
        chips.append("COILED")
    if row.get("dilution_risk"):
        chips.append("DILUTION")
    ins = sig.get("insider") or {}
    if ins.get("cluster") or ins.get("score", 0) >= 0.7:
        d = ins.get("net_dollars", 0)
        amt = (f"${d/1e6:.1f}M" if abs(d) >= 1e6 else f"${int(d/1000)}k") if d else ""
        chips.append(f"INSIDER BUY {ins.get('buyers_distinct',0)}·{amt}·{ins.get('last_buy_days_ago')}d" if amt else "INSIDER BUY")
    if (sig.get("fundamental_trends") or {}).get("revenue_trend") == "accelerating":
        chips.append("REV ACCEL")
    state = ("TRIGGERED" if row.get("compression_extreme") else "WATCHING") if lane == "compression" else None
    return {
        "symbol": row["symbol"], "lane": lane, "composite_score": composite, "score": composite,
        "families": {f: round(scores[f], 2) for f in EDGE_FAMILIES},
        "families_fired": fired, "unavailable": [f for f in EDGE_FAMILIES if not avail[f]],
        "band": band, "hold_band": band, "rr_floor": rr, "time_stop_days": tstop,
        "price": row.get("price"), "price_tier": row.get("price_tier"),
        "float_tier": row.get("float_tier"), "float_shares": row.get("float_shares"),
        "float_est": row.get("float_est"), "so_proxy": row.get("so_proxy"),
        "rel_vol": row.get("rel_vol"), "sector_name": row.get("sector_name"),
        "days_to_earnings": sig.get("days_to_earnings"),   # B3 earnings guard input
        "dilution_risk": row.get("dilution_risk"), "coiled_state": state,
        "demand_signals": gate_tags if lane == "reversal" else [],
        "catalyst": sig.get("catalyst"), "chips": chips,
        "reasons": [f"{f} {scores[f]:.2f}" for f in fired],
    }


def family_coverage(rows: list[dict[str, Any]]) -> dict[str, float]:
    """Fraction of rows on which each family's DATA is AVAILABLE (fetched, not
    fetch-failed). This is the input to lane_disable_status. (The caller decides
    WHICH rows to measure over -- universe-wide today, shortlist once GATE 1 lands.)"""
    if not rows:
        return {f: 0.0 for f in EDGE_FAMILIES}
    counts = {f: 0 for f in EDGE_FAMILIES}
    for row in rows:
        _, avail = compute_families(row)
        for f in EDGE_FAMILIES:
            if avail[f]:
                counts[f] += 1
    n = len(rows)
    return {f: round(counts[f] / n, 4) for f in EDGE_FAMILIES}


def lane_disable_status(coverage: dict[str, float],
                        threshold: float = DEGRADE_THRESHOLD) -> dict[str, dict[str, Any]]:
    """Which lanes are DISABLED because a thesis-core family is below `threshold`
    coverage. Returns {lane: {disabled, reason, degraded}} for the disabled lanes."""
    out: dict[str, dict[str, Any]] = {}
    for lane, cores in THESIS_CORE.items():
        degraded = {f: coverage.get(f, 0.0) for f in cores if coverage.get(f, 0.0) < threshold}
        if degraded:
            worst_f = min(degraded, key=degraded.get)
            out[lane] = {
                "disabled": True,
                "reason": f"{worst_f} data unavailable ({degraded[worst_f] * 100:.0f}% coverage)",
                "degraded": {f: round(c, 3) for f, c in degraded.items()},
            }
    return out


def stage1_prescore(row: dict[str, Any]) -> float:
    """GATE 1 shortlist ranker: the best available-only lane composite from what
    STAGE 1 can already see (chart + fundamental families). Deliberately PERMISSIVE
    -- no gate, no coverage floor, no require_available, no disable filter -- because
    its only job is to decide which names deserve the expensive Stage-2 fetch. It
    scores the fundamental-thesis lanes on their Stage-1-visible strength (their
    fundamental weight) so a strong-fundamental, quiet-chart name still ranks high
    enough to earn its insider/catalyst data -- otherwise the shortlist would
    silently recreate the blindness one layer up."""
    scores, avail = compute_families(row)
    best = 0.0
    for lane in LANES:
        w = _WEIGHTS[lane]
        num = sum(w[f] * scores[f] for f in EDGE_FAMILIES if avail[f] and w[f] > 0)
        den = sum(w[f] for f in EDGE_FAMILIES if avail[f] and w[f] > 0)
        if den > 0:
            best = max(best, 10.0 * num / den)
    return round(best, 3)


def evaluate_all(row: dict[str, Any], *, sector_early: bool = False,
                 sector_ps: Optional[list[float]] = None,
                 disabled: frozenset = frozenset()) -> list[dict[str, Any]]:
    if _hard_pass(row):
        return []
    scores, avail = compute_families(row, sector_early=sector_early)
    pen_pts, pen_chips = _penalties(row)
    out = []
    for lane in LANES:
        if lane in disabled:            # GATE 2: thesis-core family degraded -> lane off
            continue
        t = eval_lane(lane, row, scores, avail, pen_pts, pen_chips)
        if t:
            if sector_early and "SECTOR EARLY" not in t["chips"]:
                t["chips"].append("SECTOR EARLY")
            out.append(t)
    return out


def best_composite(row: dict[str, Any], *, sector_early: bool = False,
                   disabled: frozenset = frozenset()) -> dict[str, Any]:
    """BUG-6 support: the best achievable composite per name even if it doesn't
    trigger, + which family is missing. Powers the never-blank 'below bar' view."""
    scores, avail = compute_families(row, sector_early=sector_early)
    pen_pts, _ = _penalties(row)
    best = {"composite": 0.0, "lane": None, "fired": [], "missing": None}
    for lane in LANES:
        if lane in disabled:
            continue
        if not _eligible(lane, row):
            continue
        if any(not avail.get(req) for req in _LANE_META[lane].get("require_available", ())):
            continue
        w = _WEIGHTS[lane]
        den = sum(w[f] for f in EDGE_FAMILIES if avail[f] and w[f] > 0)
        den_all = sum(w[f] for f in EDGE_FAMILIES if w[f] > 0)
        if den <= 0 or den_all <= 0 or den / den_all < MIN_COVERAGE:
            continue
        comp = round(_clamp(10.0 * sum(w[f] * scores[f] for f in EDGE_FAMILIES if avail[f] and w[f] > 0) / den + pen_pts, 0, 10), 2)
        fired = [f for f in EDGE_FAMILIES if avail[f] and scores[f] >= FAMILY_FIRE and w[f] > 0]
        if comp > best["composite"]:
            # the highest-weight available family NOT firing = the "missing" edge
            miss = sorted([f for f in EDGE_FAMILIES if w[f] > 0 and avail[f] and scores[f] < FAMILY_FIRE],
                          key=lambda f: -w[f])
            best = {"composite": comp, "lane": lane, "fired": fired, "missing": miss[0] if miss else None}
    return best
