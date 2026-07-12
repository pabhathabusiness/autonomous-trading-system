"""
Addendum 3/4 — multi-edge small-cap scoring (replaces the ANDed-gate lanes).

The zero-trigger bug was probability collapse: every lane ANDed ~5 hard gates, so
a single missing condition killed the candidate. The fix (A3 Part 4): every name
is SCORED on a 0-10 composite built from independent EDGE FAMILIES, and triggers
only when BOTH:
    1. composite_score >= COMPOSITE_THRESHOLD (7.0, tunable)
    2. >= 3 independent edge families fire (each >= 0.5)
The 3-family rule is the anti-chase core: a lone volume spike -- one family maxed,
nothing else -- can never trigger, no matter how extreme.

Only three things stay HARD (in the universe build, not here): deathwatch
(reverse-split/dilution), $vol >= 300k, exchange-listed. Float is NEVER a gate --
each lane has a float CEILING (character), and float is a scored edge (tighter =
higher). Everything else scores; nothing else "passes".

Pure over a universe row (row + row['signals']); no I/O. The `insider` family and
news polarity land in T2 -- their inputs are read defensively here (absent -> 0).
"""

from __future__ import annotations

from typing import Any, Optional

LANES = ("special", "value", "bounce", "coiled", "runner", "hailmary")
EDGE_FAMILIES = ("volume", "structure", "compression", "trend", "fundamental",
                 "catalyst", "sector", "float", "insider")

COMPOSITE_THRESHOLD = 6.5    # F4 tune: dry-scan sample (weekend, no sector panel)
                             # understated live composites by ~0.9, so stepped 7.0->6.5
                             # (not F4's 6.0 floor -- safer on understated data).
                             # RE-VALIDATE on the full live universe + trading day.
MIN_FAMILIES = 3             # >= 3 independent families firing (each >= FAMILY_FIRE)
FAMILY_FIRE = 0.5

# A4 Part 10 (final) lane weights, incl. the insider family.
_WEIGHTS = {
    "special":  {"volume": 0.5, "structure": 1.5, "compression": 1.5, "trend": 2.0, "fundamental": 3.0, "catalyst": 1.0, "sector": 0.5, "float": 0.0, "insider": 2.0},
    "value":    {"volume": 0.5, "structure": 1.0, "compression": 1.0, "trend": 2.0, "fundamental": 3.5, "catalyst": 0.5, "sector": 0.5, "float": 0.0, "insider": 2.5},
    "bounce":   {"volume": 2.0, "structure": 3.0, "compression": 1.0, "trend": 0.0, "fundamental": 0.5, "catalyst": 1.5, "sector": 1.0, "float": 1.0, "insider": 1.5},
    "coiled":   {"volume": 1.5, "structure": 1.5, "compression": 3.5, "trend": 0.5, "fundamental": 0.0, "catalyst": 1.0, "sector": 1.0, "float": 1.0, "insider": 0.5},
    "runner":   {"volume": 3.0, "structure": 1.0, "compression": 1.5, "trend": 0.5, "fundamental": 0.0, "catalyst": 2.5, "sector": 1.0, "float": 1.5, "insider": 0.5},
    "hailmary": {"volume": 3.5, "structure": 0.5, "compression": 1.0, "trend": 0.0, "fundamental": 0.0, "catalyst": 3.0, "sector": 0.5, "float": 1.5, "insider": 0.0},
}
# F3 lane float ceilings (millions, on float_est) + price-tier gating + eligible bands.
_LANE_META = {
    "special":  {"float_ceiling": 1000, "price_tiers": ("special",),              "bands": ("medium", "position"), "hard": ("options_liquid",)},
    "value":    {"float_ceiling": 500,  "price_tiers": ("special", "low"),        "bands": ("medium", "position"), "hard": ()},
    "bounce":   {"float_ceiling": 200,  "price_tiers": ("special", "low", "sub2"),"bands": ("short", "medium"),    "hard": ()},
    "coiled":   {"float_ceiling": 100,  "price_tiers": ("special", "low", "sub2"),"bands": ("short", "medium"),    "hard": ()},
    "runner":   {"float_ceiling": 20,   "price_tiers": ("low", "sub2", "deep"),   "bands": ("short", "overnight"), "hard": ()},
    "hailmary": {"float_ceiling": 50,   "price_tiers": ("low", "sub2", "deep"),   "bands": ("short", "overnight"), "hard": ()},
}
# A6 band mechanics
_BANDS = {  # band -> (rr_floor, time_stop_days, atr_stop_mult, atr_target_mult)
    "overnight": (1.8, 2, 0.6, 1.5),
    "short":     (2.0, 5, 1.0, 2.0),
    "medium":    (2.2, 15, 1.5, 3.0),
    "position":  (2.2, 40, 2.0, 4.0),
}


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# ---------------------------------------------------------------- edge families
def _fam_volume(row, sig, dt) -> float:
    rv = row.get("rel_vol") or 0
    score = _clamp((rv - 1.0) / 2.0)              # A3 1.3 curve: 1.5x->0.25, 3x->1.0
    if dt.get("exhaustion"):                      # contracting down-volume (bounce setup)
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
    if dt.get("weekly_breakout"):                 # A6 weekly momentum (absent until A6)
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
    base = _clamp((20.0 - bb) / 20.0)             # tighter percentile = higher
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
    gm = f.get("grossMarginTTM")
    if gm is not None:
        parts.append(_clamp(gm / 50.0))
    de = f.get("debtToEquity")
    if de is not None:
        parts.append(_clamp((2.0 - de) / 2.0))
    ocf = f.get("operCashFlowPerShareTTM")
    if ocf is not None:
        parts.append(1.0 if ocf > 0 else 0.2)
    # T2 adds revenue/margin TRENDS (weighted ~40%); read defensively
    trend = sig.get("fundamental_trends") or {}
    if trend.get("revenue_trend") == "accelerating":
        parts.append(1.0)
    elif trend.get("revenue_trend") == "decelerating":
        parts.append(0.2)
    return round(sum(parts) / len(parts), 3) if parts else 0.0


def _fam_catalyst(row, sig, dt) -> float:
    # T2 replaces this with classified polarity; for now: a present, recent headline.
    cls = sig.get("catalyst_class")               # T2: {'weight': .., 'type': ..}
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
    heat = sig.get("sector_heat")                 # attached by the scan (optional)
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
    return _clamp((sig.get("insider") or {}).get("score", 0.0))   # T2 populates


def compute_families(row: dict[str, Any], *, sector_early: bool = False) -> dict[str, float]:
    sig = row.get("signals") or {}
    dt = sig.get("demand_trend") or {}
    return {
        "volume": _fam_volume(row, sig, dt),
        "structure": _fam_structure(row, sig, dt),
        "compression": _fam_compression(row, sig, dt),
        "trend": _fam_trend(row, sig, dt),
        "fundamental": _fam_fundamental(row, sig, dt),
        "catalyst": _fam_catalyst(row, sig, dt),
        "sector": _fam_sector(row, sig, dt, sector_early),
        "float": _fam_float(row, sig, dt),
        "insider": _fam_insider(row, sig, dt),
    }


# ---------------------------------------------------------------- penalties
def _penalties(row: dict[str, Any]) -> tuple[float, list[str]]:
    """Composite-scale adjustments. sub-$1 DELISTING RISK (A3 1.4) outside deep
    tier; going-concern is a HARD pass handled by the caller; insider heavy
    selling (T2)."""
    sig = row.get("signals") or {}
    pts, chips = 0.0, []
    if sig.get("delisting_risk") and row.get("price_tier") != "deep":
        pts -= 1.5
        chips.append("DELISTING RISK")
    # A4 3.1: negative-polarity headline (offering/miss/delisting). The catalyst
    # family already zeroes it; this is the extra composite drag -- the live bug fix.
    cw = (sig.get("catalyst_class") or {}).get("weight", 0.0) or 0.0
    if cw < 0:
        pts += cw
        ct = (sig.get("catalyst_class") or {}).get("type")
        chips.append("OFFERING" if ct == "offering" else "NEWS NEG")
    if (sig.get("insider") or {}).get("heavy_selling"):
        pts -= 0.5
        chips.append("INSIDER SELLING")
    return pts, chips


def _hard_pass(row: dict[str, Any]) -> Optional[str]:
    """Reasons a name is disqualified from ALL lanes (beyond universe deathwatch):
    a going_concern headline (A4 3.1)."""
    if (row.get("signals") or {}).get("going_concern"):
        return "going_concern"
    return None


def _pick_band(lane: str, row: dict[str, Any], dt: dict[str, Any]) -> str:
    eligible = _LANE_META[lane]["bands"]
    if "medium" in eligible and (dt.get("weekly_breakout") or dt.get("weekly_base")):
        return "medium"
    if "overnight" in eligible and dt.get("gap_setup"):
        return "overnight"
    return eligible[0]


def _eligible(lane: str, row: dict[str, Any]) -> bool:
    meta = _LANE_META[lane]
    fe = row.get("float_est")
    if fe is not None and fe > meta["float_ceiling"]:
        return False
    pt = row.get("price_tier")
    if meta["price_tiers"] and pt not in meta["price_tiers"]:
        return False
    for req in meta["hard"]:
        if not row.get(req):
            return False
    return True


def eval_lane(lane: str, row: dict[str, Any], families: dict[str, float],
              pen_pts: float, pen_chips: list[str]) -> Optional[dict[str, Any]]:
    if not _eligible(lane, row):
        return None
    w = _WEIGHTS[lane]
    wsum = sum(w.values()) or 1.0
    base = 10.0 * sum(families[f] * w[f] for f in EDGE_FAMILIES) / wsum
    composite = round(_clamp(base + pen_pts, 0.0, 10.0), 2)
    fired = [f for f in EDGE_FAMILIES if families[f] >= FAMILY_FIRE and w[f] > 0]
    if composite < COMPOSITE_THRESHOLD or len(fired) < MIN_FAMILIES:
        return None
    sig = row.get("signals") or {}
    dt = sig.get("demand_trend") or {}
    band = _pick_band(lane, row, dt)
    rr, tstop, _, _ = _BANDS[band]
    chips = list(pen_chips)
    if row.get("compression_extreme"):
        chips.append("COILED")
    if row.get("dilution_risk"):
        chips.append("DILUTION")
    ins = sig.get("insider") or {}
    if ins.get("cluster") or ins.get("score", 0) >= 0.7:
        n, dollars, ago = ins.get("buyers_distinct", 0), ins.get("net_dollars", 0), ins.get("last_buy_days_ago")
        chips.append(f"INSIDER BUY {n}·${int(dollars/1000)}k·{ago}d" if dollars else "INSIDER BUY")
    if (sig.get("fundamental_trends") or {}).get("revenue_trend") == "accelerating":
        chips.append("REV ACCEL")
    ct = (sig.get("catalyst_class") or {}).get("type")
    if ct in ("contract_award", "regulatory_win", "earnings_beat"):
        chips.append(ct.replace("_", " ").upper())
    if lane == "coiled" and not row.get("compression_extreme"):
        state = "WATCHING"
    elif lane == "coiled":
        state = "TRIGGERED"
    else:
        state = None
    return {
        "symbol": row["symbol"], "lane": lane, "composite_score": composite,
        "score": composite, "families": {f: round(families[f], 2) for f in EDGE_FAMILIES},
        "families_fired": fired, "band": band, "hold_band": band, "rr_floor": rr,
        "time_stop_days": tstop, "price": row.get("price"), "price_tier": row.get("price_tier"),
        "float_tier": row.get("float_tier"), "float_shares": row.get("float_shares"),
        "float_est": row.get("float_est"), "so_proxy": row.get("so_proxy"),
        "rel_vol": row.get("rel_vol"), "sector_name": row.get("sector_name"),
        "dilution_risk": row.get("dilution_risk"), "coiled_state": state,
        "catalyst": sig.get("catalyst"), "chips": chips,
        "reasons": [f"{f} {families[f]:.2f}" for f in fired],
    }


def evaluate_all(row: dict[str, Any], *, sector_early: bool = False,
                 sector_ps: Optional[list[float]] = None) -> list[dict[str, Any]]:
    """All lanes for one universe row. Returns 0-6 triggers (a name can legitimately
    score in more than one lane -- each tracked separately)."""
    if _hard_pass(row):                            # going-concern: no lane, ever
        return []
    families = compute_families(row, sector_early=sector_early)
    pen_pts, pen_chips = _penalties(row)
    out = []
    for lane in LANES:
        t = eval_lane(lane, row, families, pen_pts, pen_chips)
        if t:
            if sector_early and "SECTOR EARLY" not in t["chips"]:
                t["chips"].append("SECTOR EARLY")
            out.append(t)
    return out
