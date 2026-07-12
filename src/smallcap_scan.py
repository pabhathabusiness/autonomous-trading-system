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
from src import smallcap_trader

logger = logging.getLogger(__name__)
TRIGGERS_KEY = "sc:triggers"


def refresh_universe(db: Database, fh: FinnhubClient, **kw) -> dict[str, Any]:
    """Daily premarket build. Slow (full screen) -- callers gate on cadence."""
    return scu.build_universe(db, fh, **kw)


def scan_and_open(db: Database, fh: Optional[FinnhubClient] = None,
                  config: Optional[dict] = None, *, open_trades: bool = True) -> dict[str, Any]:
    """Evaluate lanes over the current universe, apply sector_early, open triggers.
    Returns a summary; caches the trigger set + sector heat for the page."""
    rows = db.get_smallcap_universe()

    # sector is now a SCORED FAMILY (A4), not a post-hoc bonus. Pass 1 gets
    # provisional triggers to feed sector heat; pass 2 re-scores with sector_early
    # folded into the composite (it can legitimately push a borderline name over).
    prov: list[dict[str, Any]] = []
    for row in rows:
        prov.extend(L.evaluate_all(row))
    heat = sec.compute_sector_heat(db, prov)

    triggers: list[dict[str, Any]] = []
    for row in rows:
        se = sec.is_sector_early(heat, row.get("sector_name"))
        for t in L.evaluate_all(row, sector_early=se):
            t["_signals"] = row.get("signals")   # for the opener's level math
            triggers.append(t)

    opened = 0
    if open_trades:
        # One position per symbol: a name can legitimately qualify for several lanes,
        # but the OPENER takes only its single best-composite lane (else one name
        # could open six correlated positions). The page cache below keeps them all.
        best_per_sym: dict[str, dict[str, Any]] = {}
        for t in triggers:
            s = t["symbol"]
            if s not in best_per_sym or t["score"] > best_per_sym[s]["score"]:
                best_per_sym[s] = t
        for t in sorted(best_per_sym.values(), key=lambda x: x["score"], reverse=True):
            if smallcap_trader.open_smallcap_trigger(db, t, config):
                opened += 1

    clean = [{k: v for k, v in t.items() if k != "_signals"} for t in triggers]
    db.cache_put(TRIGGERS_KEY, {"as_of": datetime.now(timezone.utc).isoformat(),
                                "triggers": clean, "sector_heat": heat})
    summary = {"universe": len(rows), "triggers": len(triggers), "opened": opened,
               "sectors": len(heat)}
    logger.info("smallcap scan: %s", summary)
    return summary


def latest_triggers(db: Database) -> dict[str, Any]:
    """Cached trigger set + sector heat for the /smallcaps page."""
    return (db.cache_get(TRIGGERS_KEY) or {}).get("payload") or {"triggers": [], "sector_heat": {}}
