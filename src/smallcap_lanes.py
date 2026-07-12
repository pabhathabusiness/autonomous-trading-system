"""
Addendum 2 -- the four small-cap lane engines.

Pure rubric + score over ONE universe row (from db.get_smallcap_universe): no
I/O, no fetching -- everything each rubric needs was gathered by the universe
builder and lives in row + row['signals']. Each lane returns a trigger dict or
None. evaluate_all() runs all four and applies the cross-cutting bonuses
(COILED +15, SECTOR EARLY +10).

The whole point of splitting the lanes (spec): after ~40 trades the per-lane
stats reveal WHICH LANE IS ACTUALLY YOURS, instead of averaging four different
edges into mush. So a name can trigger in more than one lane -- each is scored
and tracked on its own.
"""

from __future__ import annotations

from typing import Any, Optional

LANES = ("runner", "bounce", "value", "hailmary")

# band -> (label, time-stop days, R:R floor) -- floors match main-spec Lane 3
_BANDS = {
    "runner":   ("scalp (1-3d)", 3, 1.5),
    "bounce":   ("swing (1-5d)", 5, 1.8),
    "value":    ("position (3-8w)", 56, 2.0),
    "hailmary": ("speculative (caged)", 5, 1.5),
}


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _catalyst_pts(cat: Optional[dict], maxpts: float) -> float:
    """Presence (60%) + recency (40%); fresher headline scores higher."""
    if not cat:
        return 0.0
    recency = _clamp(1 - (cat.get("age_h") or 48) / 48, 0, 1)
    return round(maxpts * (0.6 + 0.4 * recency), 1)


def _trigger(lane: str, score: float, row: dict, *, components: dict,
             reasons: list[str], demand_signals: Optional[list[str]] = None) -> dict[str, Any]:
    band, tstop, rr = _BANDS[lane]
    chips = []
    if row.get("compression_extreme"):
        chips.append("COILED")
    if row.get("dilution_risk"):
        chips.append("DILUTION")
    if (row.get("float_tier")) in ("runner", "low"):
        chips.append("LOW FLOAT")
    return {
        "symbol": row["symbol"], "lane": lane, "score": round(score, 1),
        "band": band, "time_stop_days": tstop, "rr_floor": rr,
        "price": row.get("price"), "float_tier": row.get("float_tier"),
        "float_shares": row.get("float_shares"), "so_proxy": row.get("so_proxy"),
        "rel_vol": row.get("rel_vol"), "sector_name": row.get("sector_name"),
        "dilution_risk": row.get("dilution_risk"),
        "catalyst": (row.get("signals") or {}).get("catalyst"),
        "demand_signals": demand_signals or [],
        "components": components, "reasons": reasons, "chips": chips,
    }


# ------------------------------------------------------------------ LANE 1
def eval_runner(row: dict[str, Any]) -> Optional[dict[str, Any]]:
    """< 20M float explosives: float<20M + rel_vol>=3 + 48h catalyst + holding
    above prior close + no dilution. Deathwatch already excluded upstream."""
    sig = row.get("signals") or {}
    dt = sig.get("demand_trend") or {}
    cat = sig.get("catalyst")
    relvol = row.get("rel_vol") or 0
    floatM = row.get("float_shares")
    if row.get("float_tier") != "runner":
        return None
    if relvol < 3.0 or not cat or not dt.get("above_prior_close") or row.get("dilution_risk"):
        return None
    relvol_pts = 20 + 15 * _clamp((relvol - 3) / 7, 0, 1)
    cat_pts = _catalyst_pts(cat, 25)
    tight_pts = 20 * _clamp((20 - (floatM if floatM is not None else 20)) / 20, 0, 1)
    struct_pts = (8 * bool(dt.get("above_prior_close")) + 6 * bool(dt.get("above_sma20"))
                  + 6 * bool(dt.get("upper_third_close")))
    comp = {"rel_vol": round(relvol_pts, 1), "catalyst": cat_pts,
            "float_tightness": round(tight_pts, 1), "structure": struct_pts}
    return _trigger("runner", sum(comp.values()), row, components=comp,
                    reasons=[f"rel_vol {relvol}x", f"float {floatM}M", "catalyst<48h",
                             "above prior close"])


# ------------------------------------------------------------------ LANE 2
def eval_bounce(row: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Oversold at a REAL level with selling exhaustion + demand confirmation.
    RSI<30 is never the reason -- a tested level is. ALL gates required."""
    sig = row.get("signals") or {}
    dt = sig.get("demand_trend") or {}
    cat = sig.get("catalyst")
    relvol = row.get("rel_vol") or 0
    # 1. downtrend context
    if dt.get("above_sma20") is not False:
        return None
    if (dt.get("pct_off_60d_high") or 0) > -30:
        return None
    # 2. at a real level (200d SMA or a >=2x-tested swing low)
    if not dt.get("at_real_level"):
        return None
    # 3. selling exhaustion (last 3 red days < 0.7x 20d avg vol)
    if not dt.get("exhaustion"):
        return None
    # 4. demand confirmation -- >= 2 of 3 on the trigger day
    ds = []
    if relvol >= 3.0 and dt.get("upper_third_close"):
        ds.append("relvol_upperthird")
    if dt.get("undercut_reclaim"):
        ds.append("undercut_reclaim")
    if dt.get("reclaim_prior_high"):
        ds.append("reclaim_prior_high")
    if len(ds) < 2:
        return None
    # 5. no dilution
    if row.get("dilution_risk"):
        return None
    comp = {
        "demand_signals": round(30 * _clamp(len(ds) / 3, 0, 1), 1),
        "level_quality": round(25 * (dt.get("level_quality") or 0), 1),
        "exhaustion": 20.0,
        "rel_vol": round(15 * _clamp(relvol / 5, 0, 1), 1),
        "catalyst": 10.0 if cat else 0.0,
    }
    return _trigger("bounce", sum(comp.values()), row, components=comp, demand_signals=ds,
                    reasons=[f">=30% off 60d high", "at tested level", "sellers exhausted",
                             f"{len(ds)}/3 demand signals"])


# ------------------------------------------------------------------ LANE 3
def _runway_quarters(f: dict[str, Any]) -> Optional[float]:
    cash = f.get("cashPerShareQuarterly")
    ocf = f.get("operCashFlowPerShareTTM")
    if cash is None or ocf is None or ocf >= 0:
        return None
    burn_q = abs(ocf) / 4
    return cash / burn_q if burn_q > 0 else None


def eval_value(row: dict[str, Any], sector_ps: Optional[list[float]] = None) -> Optional[dict[str, Any]]:
    """Cheap != garbage. FUNDAMENTALS required; any missing field => DISQUALIFIED
    (no proxies -- a value thesis on guessed numbers is worthless)."""
    sig = row.get("signals") or {}
    dt = sig.get("demand_trend") or {}
    f = sig.get("fundamentals") or {}
    cat = sig.get("catalyst")
    req = ("revenueTTM_musd", "revenueGrowthYoY", "grossMarginTTM", "debtToEquity",
           "operCashFlowPerShareTTM")
    if any(f.get(k) is None for k in req):
        return None
    ocf = f["operCashFlowPerShareTTM"]
    runway_q = _runway_quarters(f)
    runway_ok = ocf > 0 or (runway_q is not None and runway_q > 4)
    # hard rubric
    if not (f["revenueTTM_musd"] > 20 and f["revenueGrowthYoY"] > 0):
        return None
    if f["grossMarginTTM"] <= 15 or not runway_ok or f["debtToEquity"] >= 2.0:
        return None
    if not (dt.get("above_sma20") and dt.get("above_sma50") and dt.get("sma50_slope_up")):
        return None
    if dt.get("recent_runner"):
        return None
    if row.get("dilution_risk"):
        return None
    # scores
    fund_composite = (
        _clamp(f["revenueGrowthYoY"] / 50, 0, 1) + _clamp(f["grossMarginTTM"] / 50, 0, 1)
        + (1.0 if ocf > 0 else _clamp((runway_q or 0) / 8, 0, 1))
        + _clamp((2.0 - f["debtToEquity"]) / 2.0, 0, 1)
    ) / 4
    consec = row.get("consecutive_up_weeks") or 0
    trend_q = 0.6 + 0.4 * _clamp(consec / 8, 0, 1)
    # valuation vs sector: lower P/S than peers => higher score; neutral if unknown
    val_q = 0.5
    ps = f.get("psTTM")
    if ps is not None and sector_ps and len(sector_ps) >= 3:
        below = sum(1 for p in sector_ps if p is not None and ps <= p)
        val_q = below / len(sector_ps)
    comp = {"fundamentals": round(40 * fund_composite, 1), "trend": round(30 * trend_q, 1),
            "valuation": round(20 * val_q, 1), "catalyst": 10.0 if cat else 0.0}
    return _trigger("value", sum(comp.values()), row, components=comp,
                    reasons=[f"rev ${f['revenueTTM_musd']}M +{f['revenueGrowthYoY']}%",
                             f"gross margin {f['grossMarginTTM']}%",
                             "positive op-CF" if ocf > 0 else f"runway {round(runway_q,1)}q",
                             f"D/E {f['debtToEquity']}"])


# ------------------------------------------------------------------ LANE 4
def eval_hailmary(row: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Explicitly speculative lottery ticket: extreme rel_vol (>=5) + catalyst +
    float<30M, WITHOUT the demand/exhaustion structure. Caged at open (fixed
    notional, max 2 open, permanently paper) -- that's enforced by the opener."""
    sig = row.get("signals") or {}
    cat = sig.get("catalyst")
    relvol = row.get("rel_vol") or 0
    if relvol < 5.0 or not cat or row.get("float_tier") not in ("runner", "low"):
        return None
    floatM = row.get("float_shares")
    comp = {"rel_vol": round(50 * _clamp(relvol / 10, 0, 1), 1),
            "catalyst": _catalyst_pts(cat, 30),
            "float_tightness": round(20 * _clamp((30 - (floatM if floatM is not None else 30)) / 30, 0, 1), 1)}
    t = _trigger("hailmary", sum(comp.values()), row, components=comp,
                 reasons=[f"rel_vol {relvol}x (extreme)", f"float {floatM}M", "catalyst<48h",
                          "CAGED: fixed size, max 2 open, permanently paper"])
    t["caged"] = True
    return t


_EVALUATORS = {"runner": eval_runner, "bounce": eval_bounce,
               "value": eval_value, "hailmary": eval_hailmary}


def evaluate_all(row: dict[str, Any], *, sector_early: bool = False,
                 sector_ps: Optional[list[float]] = None) -> list[dict[str, Any]]:
    """All four lanes for one row + cross-cutting bonuses. Returns 0-4 triggers."""
    out = []
    for lane, fn in _EVALUATORS.items():
        trig = fn(row, sector_ps) if lane == "value" else fn(row)
        if not trig:
            continue
        # cross-cutting (spec C+B): COILED +15, SECTOR EARLY +10
        if row.get("compression_extreme"):
            trig["score"] = round(trig["score"] + 15, 1)
            trig["components"]["coiled_bonus"] = 15.0
        if sector_early:
            trig["score"] = round(trig["score"] + 10, 1)
            trig["components"]["sector_early_bonus"] = 10.0
            trig["chips"].append("SECTOR EARLY")
        out.append(trig)
    return out
