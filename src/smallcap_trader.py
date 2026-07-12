"""
Addendum 2 -- open a small-cap lane trigger as a QUARANTINED paper trade.

book='smallcap', source='smallcap', strategy=lane (so the open_paper_trade
idempotency guard becomes one open trade per symbol+lane). NEVER a real or Alpaca
order -- these are simulated paper_trades rows the existing price-replay resolver
closes, so the paper-vs-real wall is untouched. The Hail-Mary lane is caged:
fixed notional, max 2 open, permanently paper.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from src.database import Database

logger = logging.getLogger(__name__)

# fixed paper notional per lane ($). Hail-Mary is fixed + never scaled (the cage).
_NOTIONAL = {"reversal": 3000.0, "breakout": 3000.0, "compression": 2500.0,
             "emerging_strength": 3000.0, "hidden_value": 4000.0, "turnaround": 3000.0}
_DEEP_MAX_OPEN = 3          # deep tier ($0.20-1) fixed tiny notional, max 3 open (no lane
_DEEP_NOTIONAL = 800.0      # currently accepts deep, so this is a defensive guard)
# lane stop floor (fraction below entry) when structure is unavailable
_STOP_PCT = {"runner": 0.08, "bounce": 0.07, "value": 0.15, "hailmary": 0.15}


def _levels(trigger: dict[str, Any]) -> tuple[float, float, float]:
    """entry / stop / target (long only). Stop from structure where available
    (bounce: under the level; value: under 50d SMA), else a lane % floor. Target
    = entry + rr_floor * risk, so R:R always clears the band floor."""
    entry = float(trigger["price"])
    lane = trigger["lane"]
    rr = trigger.get("rr_floor", 1.5)
    dt = (trigger.get("_signals") or {}).get("demand_trend") or {}
    stop = None
    if lane == "bounce":
        lvl = dt.get("prior10_low")
        if lvl and lvl < entry:
            stop = lvl * 0.98            # just under the tested level
    elif lane == "value":
        sma50 = dt.get("sma50")
        if sma50 and sma50 < entry:
            stop = sma50 * 0.95
    if stop is None or stop >= entry:
        stop = entry * (1 - _STOP_PCT.get(lane, 0.10))
    risk = entry - stop
    return round(entry, 4), round(stop, 4), round(entry + rr * risk, 4)


def open_smallcap_trigger(db: Database, trigger: dict[str, Any],
                          config: Optional[dict] = None) -> Optional[int]:
    """Open one trigger as a book='smallcap' paper trade. Returns the trade id,
    or None if skipped (Hail-Mary cage full / duplicate open for symbol+lane)."""
    lane = trigger["lane"]
    # deep tier ($0.20-1) is caged at max 3 open across the whole tier.
    if trigger.get("price_tier") == "deep":
        deep_open = sum(1 for t in db.get_smallcap_trades(status="open")
                        if (t.get("price_tier") == "deep"))
        if deep_open >= _DEEP_MAX_OPEN:
            logger.info("deep-tier cage full (%d open) -- skipping %s", _DEEP_MAX_OPEN, trigger.get("symbol"))
            return None
    entry, stop, target = _levels(trigger)
    if entry <= 0 or stop <= 0 or target <= entry:
        return None
    if trigger.get("price_tier") == "deep":
        notional = _DEEP_NOTIONAL            # fixed tiny, never scaled
    else:
        notional = (((config or {}).get("smallcap", {}) or {}).get("notional", {}) or {}).get(
            lane, _NOTIONAL.get(lane, 2500.0))
    shares = round(notional / entry, 2) if entry > 0 else 0
    tj = {k: trigger.get(k) for k in ("lane", "composite_score", "band", "reasons", "chips",
                                      "catalyst", "families", "families_fired", "coiled_state",
                                      "float_tier", "float_est", "float_shares", "rel_vol")}
    return db.open_paper_trade({
        "symbol": trigger["symbol"], "strategy": lane, "direction": "long",
        "sector_name": trigger.get("sector_name"),
        "entry_price": entry, "stop_loss": stop, "target_price": target,
        "expected_timeframe": trigger.get("band"), "max_hold_days": trigger.get("time_stop_days", 5),
        "book": "smallcap", "source": "smallcap", "lane": lane,
        "lane_score": trigger.get("score"), "composite_score": trigger.get("composite_score"),
        "price_tier": trigger.get("price_tier"), "hold_band": trigger.get("band"),
        "trigger_json": json.dumps(tj),
        "shares": shares, "position_value": round(shares * entry, 2),
        "planned_rr": trigger.get("rr_floor"),
        "process_grade": None,   # small-caps use per-lane stats, not the A-F grade
    })
