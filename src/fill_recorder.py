"""
B1 fill recorder: turn an Alpaca order response into the FILL fields we record
(fill_price, slippage_bps, filled_qty, partial_fill, was_rejected, time_to_fill,
gap_through_stop) -- so we log the FILL, not the intent.

A freshly-submitted bracket is usually status 'accepted'/'new' (NOT filled). We
record the submission first, then capture fill metrics only after reconciliation
(AlpacaClient.get_order). A _post error / None response is treated as a NON-fill
(never a phantom open).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

_REJECT = {"rejected", "canceled", "cancelled", "expired", "suspended",
           "stopped", "done_for_day"}


def _f(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _parse_ts(v: Any) -> Optional[datetime]:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def _dump(obj: Any) -> Optional[str]:
    try:
        return json.dumps(obj, default=str)[:4000]
    except (TypeError, ValueError):
        return None


def is_error(resp: Optional[dict[str, Any]]) -> bool:
    """A _post error / disabled / no-response => NON-fill (never record an open)."""
    if not resp or not isinstance(resp, dict):
        return True
    return "error" in resp or resp.get("status") == "disabled"


def slippage_bps(fill_price: Optional[float], planned: Optional[float]) -> Optional[float]:
    if fill_price is None or not planned:
        return None
    return round((fill_price - planned) / planned * 1e4, 1)


def parse_submission(resp: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Fields to record at submission (before fill)."""
    if is_error(resp):
        return {"was_rejected": 1, "order_status": "rejected",
                "broker_order_id": None, "client_order_id": None}
    status = (resp.get("status") or "").lower()
    return {
        "broker_order_id": resp.get("id"),
        "client_order_id": resp.get("client_order_id"),
        "order_status": status or "submitted",
        "was_rejected": 1 if status in _REJECT else 0,
    }


def parse_fill(order: Optional[dict[str, Any]], *, planned_entry: Optional[float],
               requested_qty: Optional[float], submitted_at: Optional[str]) -> dict[str, Any]:
    """Entry-fill metrics from a reconciled order object. Returns only status when
    not yet filled (never fabricates a fill)."""
    if is_error(order):
        return {"was_rejected": 1, "order_status": "rejected"}
    status = (order.get("status") or "").lower()
    out: dict[str, Any] = {"order_status": status,
                           "was_rejected": 1 if status in _REJECT else 0}
    filled_qty = _f(order.get("filled_qty")) or 0.0
    fill_price = _f(order.get("filled_avg_price"))
    if fill_price is None or filled_qty <= 0:
        return out                       # not filled yet -- nothing to record
    out["fill_price"] = fill_price
    out["filled_qty"] = filled_qty
    out["slippage_bps"] = slippage_bps(fill_price, planned_entry)
    if requested_qty:
        out["partial_fill"] = 1 if filled_qty < float(requested_qty) else 0
    sub = _parse_ts(submitted_at) or _parse_ts(order.get("submitted_at"))
    fil = _parse_ts(order.get("filled_at"))
    if sub and fil:
        out["time_to_fill"] = round((fil - sub).total_seconds(), 2)
    out["is_real"] = 1
    return out


def parse_exit_fill(order: Optional[dict[str, Any]], *, planned_exit: Optional[float],
                    stop_price: Optional[float], direction: str = "long",
                    submitted_at: Optional[str] = None) -> dict[str, Any]:
    """Exit-side fill metrics incl. gap_through_stop (exit filled materially worse
    than the stop level -- a real slippage-through-stop event)."""
    if is_error(order):
        return {}
    fill_price = _f(order.get("filled_avg_price"))
    if fill_price is None:
        return {}
    out: dict[str, Any] = {"exit_fill_price": fill_price,
                           "exit_slippage_bps": slippage_bps(fill_price, planned_exit)}
    sub = _parse_ts(submitted_at) or _parse_ts(order.get("submitted_at"))
    fil = _parse_ts(order.get("filled_at"))
    if sub and fil:
        out["exit_time_to_fill"] = round((fil - sub).total_seconds(), 2)
    if stop_price:
        tol = 0.001                      # 0.1% past the stop = a real gap-through
        if direction == "long":
            out["gap_through_stop"] = 1 if fill_price < stop_price * (1 - tol) else 0
        else:                            # short: stop is above; gap fills higher
            out["gap_through_stop"] = 1 if fill_price > stop_price * (1 + tol) else 0
    return out


def find_filled_exit_leg(order: Optional[dict[str, Any]]) -> Optional[tuple[dict, str]]:
    """From a bracket PARENT order's legs, the first FILLED exit leg + its kind
    ('stop' | 'target'), or None. Requires the order fetched with nested=true."""
    if not order or not isinstance(order, dict):
        return None
    for leg in (order.get("legs") or []):
        if (leg.get("status") or "").lower() != "filled":
            continue
        if _f(leg.get("filled_avg_price")) is None:
            continue
        typ = (leg.get("order_type") or leg.get("type") or "").lower()
        kind = "stop" if ("stop" in typ or leg.get("stop_price")) else "target"
        return leg, kind
    return None


def compute_real_close(entry_fill: Optional[float], exit_fill: Optional[float],
                       stop: Optional[float], qty: Optional[float],
                       direction: str = "long") -> dict[str, Any]:
    """Realized $ / % / R from the ACTUAL entry and exit fills."""
    if not entry_fill or not exit_fill or not qty:
        return {}
    sign = 1.0 if direction != "short" else -1.0
    pnl = sign * (exit_fill - entry_fill) * qty
    ret = sign * (exit_fill / entry_fill - 1.0) * 100.0 if entry_fill else None
    risk_ps = abs(entry_fill - stop) if stop else None
    r = (sign * (exit_fill - entry_fill) / risk_ps) if risk_ps else None
    return {"real_pnl_usd": round(pnl, 2),
            "real_return_pct": round(ret, 2) if ret is not None else None,
            "real_r_multiple": round(r, 2) if r is not None else None}


def compute_sim_close(planned_entry: Optional[float], exit_level: Optional[float],
                      shares: Optional[float], stop: Optional[float],
                      direction: str = "long") -> dict[str, Any]:
    """The SIM counterfactual: fill AT the planned entry and exit AT the plan
    level the bracket hit -- what the internal sim would have recorded. Stored in
    pnl_usd/return_pct/r_multiple beside the real_* fills for sim_vs_real."""
    if not planned_entry or not exit_level or not shares:
        return {}
    sign = 1.0 if direction != "short" else -1.0
    risk_ps = abs(planned_entry - stop) if stop else None
    return {"pnl_usd": round(sign * (exit_level - planned_entry) * shares, 2),
            "return_pct": round(sign * (exit_level / planned_entry - 1.0) * 100.0, 2),
            "r_multiple": (round(sign * (exit_level - planned_entry) / risk_ps, 2)
                           if risk_ps else None)}


# ---------------------------------------------------------------- DB write helpers
def record_submission(db, trade_id: int, resp: Optional[dict[str, Any]], *,
                      planned_entry: Optional[float] = None) -> dict[str, Any]:
    fields = parse_submission(resp)
    db.record_open_fill(trade_id, broker_order_id=fields.get("broker_order_id"),
                        order_status=fields.get("order_status"),
                        was_rejected=fields.get("was_rejected"))
    db.insert_order_fill(trade_id=trade_id, broker_order_id=fields.get("broker_order_id"),
                         leg="entry", event_type="submitted", raw_json=_dump(resp))
    return fields


def record_open_fill(db, trade_id: int, order: Optional[dict[str, Any]], *,
                     planned_entry: Optional[float], requested_qty: Optional[float],
                     submitted_at: Optional[str]) -> dict[str, Any]:
    fields = parse_fill(order, planned_entry=planned_entry, requested_qty=requested_qty,
                        submitted_at=submitted_at)
    db.record_open_fill(trade_id, **fields)
    if fields.get("fill_price") is not None:
        db.insert_order_fill(trade_id=trade_id, broker_order_id=(order or {}).get("id"),
                             leg="entry", event_type="fill", qty=fields.get("filled_qty"),
                             price=fields.get("fill_price"), raw_json=_dump(order))
    return fields


def record_exit_fill(db, trade_id: int, order: Optional[dict[str, Any]], *,
                     planned_exit: Optional[float], stop_price: Optional[float],
                     direction: str = "long", submitted_at: Optional[str] = None) -> dict[str, Any]:
    fields = parse_exit_fill(order, planned_exit=planned_exit, stop_price=stop_price,
                             direction=direction, submitted_at=submitted_at)
    if fields:
        db.record_exit_fill(trade_id, **fields)
        db.insert_order_fill(trade_id=trade_id, broker_order_id=(order or {}).get("id"),
                             leg="exit", event_type="fill",
                             price=fields.get("exit_fill_price"), raw_json=_dump(order))
    return fields
