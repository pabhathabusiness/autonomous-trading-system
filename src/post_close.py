"""
Post-close enrichment (Lane 1/2 derived fields for trades closed going forward).

Fills exit_reason, mae_r/mfe_r and quadrant on CLOSED paper trades that are
missing them. Runs from the scheduler's monitor tick, AFTER the close paths
have done their work -- resolve_open / close_on_live_cross / close_paper_trade
are deliberately untouched (spec ground rule); this derives from what they
already persisted, using the same comparison logic they use.

Every write targets a currently-NULL column only (enrich-only, never overwrite).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import yfinance as yf

logger = logging.getLogger(__name__)

# closes record the exact plan level (rounded 4dp), so 0.1% relative is generous
_TOL = 0.001
_GE_B = ("A", "B")


def _near(a: Optional[float], b: Optional[float]) -> bool:
    return bool(a is not None and b and abs(a - b) / abs(b) <= _TOL)


def derive_exit_reason(t: dict[str, Any]) -> str:
    """Mirror of the close functions' branch order: stop checked FIRST, then
    target; resolve_open's age-out branch is the only source of 'timeout'."""
    ep = t.get("exit_price")
    if _near(ep, t.get("stop_loss")):
        return "stop"
    if _near(ep, t.get("target_price")):
        return "target"
    try:
        days_held = (datetime.fromisoformat(t["exit_date"])
                     - datetime.fromisoformat(t["entry_date"])).days
    except (ValueError, TypeError, KeyError):
        return "unknown"
    return "timeout" if days_held >= (t.get("max_hold_days") or 21) else "unknown"


def derive_mae_mfe(t: dict[str, Any]) -> Optional[tuple[float, float]]:
    """MAE/MFE in R from daily OHLC between open and close (spec Lane 1.3);
    direction-inverted for shorts. None when data is unavailable (retried on a
    later tick, harmless)."""
    entry, stop = t.get("entry_price"), t.get("stop_loss")
    risk = abs((entry or 0) - (stop or 0))
    if not entry or risk <= 0:
        return None
    try:
        d0 = datetime.fromisoformat(t["entry_date"]).date()
        d1 = datetime.fromisoformat(t["exit_date"]).date()
        hist = yf.Ticker(t["symbol"]).history(
            start=d0.isoformat(), end=(d1 + timedelta(days=1)).isoformat(),
            interval="1d", auto_adjust=True)
    except Exception:
        return None
    if hist is None or hist.empty:
        return None
    lo, hi = float(hist["Low"].min()), float(hist["High"].max())
    if t.get("direction") == "short":
        mae, mfe = (entry - hi) / risk, (entry - lo) / risk
    else:
        mae, mfe = (lo - entry) / risk, (hi - entry) / risk
    return round(mae, 2), round(mfe, 2)


def derive_quadrant(t: dict[str, Any]) -> Optional[str]:
    """Spec 2.4: (grade >= B) x outcome. Live process grade wins; retro grade
    stands in for legacy rows. UNGRADED counts as below B."""
    outcome = t.get("outcome")
    if outcome not in ("win", "loss"):
        return None
    g = t.get("process_grade")
    if not g or g == "UNGRADED":
        g = t.get("retro_grade")
    good = g in _GE_B
    if outcome == "win":
        return "skill_win" if good else "lucky_win"
    return "good_loss" if good else "bad_loss"


def enrich_closed(db) -> int:
    """Fill exit_reason / mae_r+mfe_r / quadrant on closed rows missing them.
    Returns how many rows were touched."""
    rows = [t for t in db.get_paper_trades(status="closed")
            if t.get("exit_reason") is None or t.get("quadrant") is None
            or (t.get("mae_r") is None and t.get("mfe_r") is None)]
    touched = 0
    for t in rows:
        fields: dict[str, Any] = {}
        if t.get("exit_reason") is None:
            fields["exit_reason"] = derive_exit_reason(t)
        if t.get("mae_r") is None and t.get("mfe_r") is None:
            mm = derive_mae_mfe(t)
            if mm:
                fields["mae_r"], fields["mfe_r"] = mm
        if t.get("quadrant") is None:
            q = derive_quadrant(t)
            if q:
                fields["quadrant"] = q
        if fields:
            db.enrich_paper_trade(t["id"], **fields)
            touched += 1
    if touched:
        logger.info("post_close: enriched %d closed trades", touched)
    return touched
