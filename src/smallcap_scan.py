"""
Addendum 2 -- small-cap scan orchestration.

Two responsibilities, split by cadence:
  refresh_universe() -- the slow daily premarket screen+enrich (build_universe).
  scan_and_open()    -- fast: read the universe rows, evaluate the four lanes,
                        apply the sector_early bonus (needs the full trigger set,
                        so it's a second pass), and open each trigger as a
                        quarantined paper trade.

Everything here reads/writes ONLY small-cap surfaces (smallcap_universe, the
'smallcap' book, sc:* cache keys). Nothing touches the main book.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.database import Database
from src.finnhub_client import FinnhubClient
from src import smallcap_universe as scu, smallcap_lanes as L, smallcap_sector as sec
from src import smallcap_trader, order_executor

logger = logging.getLogger(__name__)
TRIGGERS_KEY = "sc:triggers"


def _algo_candidate(trigger: dict[str, Any], avg_dollar_vol: Optional[float]) -> Optional[dict[str, Any]]:
    """Map a live trigger (with _signals attached) to an order_executor candidate,
    reusing the SIM opener's exact entry/stop/target level math so the real order
    mirrors the sim (giving the sim_vs_real comparison on the same levels)."""
    entry, stop, target = smallcap_trader._levels(trigger)
    if entry <= 0 or stop <= 0 or target <= entry:
        return None
    return {
        "symbol": trigger["symbol"], "entry": entry, "stop": stop, "target": target,
        "sector": trigger.get("sector_name"), "lane": trigger.get("lane"),
        "quality": trigger.get("composite_score") or trigger.get("score") or 7.5,
        "avg_dollar_vol": avg_dollar_vol, "direction": "long",
        "composite_score": trigger.get("composite_score"), "lane_score": trigger.get("score"),
        "price_tier": trigger.get("price_tier"), "hold_band": trigger.get("band"),
        "rel_vol": trigger.get("rel_vol"), "strategy": "smallcap",
    }


def refresh_universe(db: Database, fh: FinnhubClient, **kw) -> dict[str, Any]:
    """Daily premarket build. Slow (full screen) -- callers gate on cadence."""
    return scu.build_universe(db, fh, **kw)


def scan_and_open(db: Database, fh: Optional[FinnhubClient] = None,
                  config: Optional[dict] = None, *, open_trades: bool = True,
                  alpaca: Any = None, risk_mgr: Any = None) -> dict[str, Any]:
    """Evaluate lanes over the current universe, apply sector_early, open triggers.
    Returns a summary; caches the trigger set + sector heat for the page.

    When alpaca.auto_place is ON (default OFF) and a live Alpaca client + risk
    manager are supplied, the same best-per-symbol triggers are ALSO placed as
    real Alpaca PAPER bracket orders through order_executor (risk gate + paper
    wall enforced inside submit_bracket_order). auto_place OFF -> sim only."""
    rows = db.get_smallcap_universe()

    # GATE 2: measure per-family data coverage, then DISABLE any lane whose
    # thesis-core family is degraded (e.g. insider at 0% -> turnaround +
    # hidden_value off). A disabled lane never fires, so it can never mislabel a
    # setup into the track record. lane_status is cached for the page.
    coverage = L.family_coverage(rows)
    disabled_status = L.lane_disable_status(coverage)
    disabled = frozenset(disabled_status)

    # sector is now a SCORED FAMILY (A4), not a post-hoc bonus. Pass 1 gets
    # provisional triggers to feed sector heat; pass 2 re-scores with sector_early
    # folded into the composite (it can legitimately push a borderline name over).
    prov: list[dict[str, Any]] = []
    for row in rows:
        prov.extend(L.evaluate_all(row, disabled=disabled))
    heat = sec.compute_sector_heat(db, prov)

    triggers: list[dict[str, Any]] = []
    for row in rows:
        se = sec.is_sector_early(heat, row.get("sector_name"))
        for t in L.evaluate_all(row, sector_early=se, disabled=disabled):
            t["_signals"] = row.get("signals")   # for the opener's level math
            triggers.append(t)

    # One position per symbol: a name can legitimately qualify for several lanes,
    # but the OPENER takes only its single best-composite lane (else one name
    # could open six correlated positions). The page cache below keeps them all.
    best_per_sym: dict[str, dict[str, Any]] = {}
    for t in triggers:
        s = t["symbol"]
        if s not in best_per_sym or t["score"] > best_per_sym[s]["score"]:
            best_per_sym[s] = t
    ranked = sorted(best_per_sym.values(), key=lambda x: x["score"], reverse=True)

    opened = 0
    if open_trades:
        for t in ranked:
            if smallcap_trader.open_smallcap_trigger(db, t, config):
                opened += 1

    # B1: place the SAME best-per-symbol triggers as REAL Alpaca PAPER orders --
    # but ONLY when alpaca.auto_place is ON (default OFF) and a live client + risk
    # manager are supplied. The 3 fail-closed gates fire inside submit_bracket_order.
    algo = None
    auto_place = bool(((config or {}).get("alpaca") or {}).get("auto_place", False))
    if (open_trades and auto_place and alpaca is not None
            and getattr(alpaca, "enabled", False) and risk_mgr is not None):
        dvol = {r["symbol"]: r.get("avg_dollar_vol_20d") for r in rows}
        cands = [c for c in (_algo_candidate(t, dvol.get(t["symbol"])) for t in ranked) if c]
        algo = order_executor.execute_candidates(db, alpaca, risk_mgr, config, cands)

    clean = [{k: v for k, v in t.items() if k != "_signals"} for t in triggers]
    # lane_status: every lane's enabled/disabled state + the reason, so each tab
    # can say plainly why it's empty (GATE 2). Chart lanes are always enabled.
    lane_status = {lane: (disabled_status[lane] if lane in disabled_status
                          else {"disabled": False}) for lane in L.LANES}
    db.cache_put(TRIGGERS_KEY, {"as_of": datetime.now(timezone.utc).isoformat(),
                                "triggers": clean, "sector_heat": heat,
                                "lane_status": lane_status, "family_coverage": coverage})
    summary = {"universe": len(rows), "triggers": len(triggers), "opened": opened,
               "sectors": len(heat), "disabled_lanes": sorted(disabled)}
    if algo is not None:
        summary["algo_placed"] = algo.get("placed", 0)
        summary["algo_refused"] = algo.get("refused", 0)
    logger.info("smallcap scan: %s", summary)
    return summary


def latest_triggers(db: Database) -> dict[str, Any]:
    """Cached trigger set + sector heat for the /smallcaps page."""
    return (db.cache_get(TRIGGERS_KEY) or {}).get("payload") or {"triggers": [], "sector_heat": {}}
