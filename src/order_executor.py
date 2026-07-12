"""
B1 order executor: place APPROVED algo candidates as REAL Alpaca PAPER bracket
orders. This is the ONLY place the scheduler auto-places orders, and it runs only
when config alpaca.auto_place is ON (default OFF).

Per candidate: size (RiskManager) -> build RiskContext from live equity + DB
exposure -> risk_gate.evaluate -> (if approved) insert the trade row -> submit
(all 3 fail-closed gates fire inside submit_bracket_order) -> record the fill.

FAIL SAFE at every layer:
  - account halted (daily-loss / drawdown)     -> refuse the whole batch
  - equity read fails                          -> refuse the whole batch
  - a control fails / data missing             -> refuse that candidate
  - a broker error / timeout                   -> mark the row rejected (no phantom)

The trade row is inserted BEFORE the POST so (a) the next candidate in the batch
sees it in the caps and (b) a crash mid-POST leaves an auditable record. The SIM
number is kept beside the real fill (paper_trader resolves entry_price/return_pct/
pnl_usd as before; the real_* columns hold the broker truth) for sim_vs_real.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src import fill_recorder, risk_gate, risk_state

logger = logging.getLogger(__name__)


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_et_date() -> str:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    except Exception:
        from datetime import timedelta
        return (datetime.now(timezone.utc) - timedelta(hours=4)).date().isoformat()


def _client_order_id(c: dict[str, Any], account_type: str) -> str:
    """Deterministic idempotency key: same symbol+lane+ET-day => same id, so a
    retry after a POST timeout can never create a duplicate real bracket."""
    lane = c.get("lane") or "none"
    return f"{account_type}-{c['symbol']}-{lane}-{_now_et_date()}"


def execute_candidates(db, alpaca, risk_mgr, config, candidates: list[dict[str, Any]],
                       *, account_type: str = "algo") -> dict[str, Any]:
    """Place approved candidates. Returns a summary. Never raises for a single
    candidate -- failures are captured per-row."""
    out: dict[str, Any] = {"placed": 0, "refused": 0, "errors": 0, "results": []}
    if not candidates:
        return out

    # batch-level fail-safe gates (also enforced per-order inside submit)
    if risk_state.is_halted(db, account_type):
        out["halted"] = True
        out["refused"] = len(candidates)
        logger.warning("order_executor: account '%s' halted -- refusing %d candidates",
                       account_type, len(candidates))
        return out
    equity = alpaca.account_equity()
    if equity is None:
        out["no_equity"] = True
        out["refused"] = len(candidates)
        logger.warning("order_executor: no equity read -- refusing all (fail safe)")
        return out
    out["equity"] = equity

    for c in candidates:
        try:
            res = _execute_one(db, alpaca, risk_mgr, config, c, account_type, equity)
        except Exception as exc:                       # never let one candidate break the batch
            logger.exception("order_executor: candidate %s failed", c.get("symbol"))
            res = {"symbol": c.get("symbol"), "outcome": "error", "reason": str(exc)}
        out["results"].append(res)
        out[{"placed": "placed", "refused": "refused"}.get(res["outcome"], "errors")] += 1
    logger.info("order_executor: placed=%d refused=%d errors=%d",
                out["placed"], out["refused"], out["errors"])
    return out


def _execute_one(db, alpaca, risk_mgr, config, c: dict[str, Any],
                 account_type: str, equity: float) -> dict[str, Any]:
    symbol = c["symbol"]
    entry, stop, target = float(c["entry"]), float(c["stop"]), float(c["target"])
    side = "sell" if c.get("direction") == "short" else "buy"

    # 1. risk-based position sizing
    sizing = risk_mgr.calculate_position_size(
        account_type, entry, stop, float(c.get("quality", 7.5)), equity)
    if not sizing:
        return {"symbol": symbol, "outcome": "refused", "reason": "sizing returned None"}
    shares = int(sizing["shares"])

    # 2. evaluate the 7 controls against live exposure (includes rows already
    #    submitted earlier in THIS batch, since they were inserted at submission)
    ctx = risk_gate.RiskContext(
        account_type=account_type, symbol=symbol, equity=equity, entry=entry, stop=stop,
        target=target, shares=shares, sector=c.get("sector"), lane=c.get("lane"),
        config=config, open_risk=db.sum_open_risk(account_type),
        sector_counts=db.count_open_by_sector(account_type),
        lane_notional=db.open_notional_by_lane(account_type),
        halted=risk_state.is_halted(db, account_type),
        avg_dollar_vol=c.get("avg_dollar_vol"), rel_vol=c.get("rel_vol"),
        days_to_earnings=c.get("days_to_earnings"))
    decision = risk_gate.evaluate(ctx)
    if not decision.approved:
        return {"symbol": symbol, "outcome": "refused", "reason": decision.reason,
                "checks": decision.checks}

    # 3. idempotency: same symbol+lane+day => one order only
    coid = _client_order_id(c, account_type)
    if db.find_algo_trade_by_client_order_id(coid):
        return {"symbol": symbol, "outcome": "refused", "reason": "duplicate client_order_id"}

    # 4. insert the trade row BEFORE the POST (so caps see it; crash leaves a record)
    submitted_at = _iso()
    trade_id = db.insert_algo_trade({
        "symbol": symbol, "account_type": account_type, "book": "algo",
        "direction": c.get("direction", "long"), "sector_name": c.get("sector"),
        "entry_price": entry, "stop_loss": stop, "target_price": target,
        "shares": shares, "position_value": round(shares * entry, 2),
        "lane": c.get("lane"), "composite_score": c.get("composite_score"),
        "lane_score": c.get("lane_score"), "price_tier": c.get("price_tier"),
        "hold_band": c.get("hold_band"), "strategy": c.get("strategy", "smallcap"),
        "trigger_json": c.get("trigger_json"), "client_order_id": coid,
        "order_status": "submitting", "submitted_at": submitted_at,
        "is_real": 1, "status": "open",
    })

    # 5. submit -- all 3 fail-closed gates run inside submit_bracket_order
    try:
        resp = alpaca.submit_bracket_order(
            symbol=symbol, qty=shares, side=side, entry_price=entry, stop_price=stop,
            target_price=target, account_type=account_type, risk_decision=decision,
            client_order_id=coid)
    except Exception as exc:
        # gate raised (should not, we pre-checked) or transport error: mark the row
        # rejected so it stops counting toward caps, and surface it.
        db.record_open_fill(trade_id, was_rejected=1, order_status="error")
        logger.warning("order_executor: submit raised for %s: %s", symbol, exc)
        return {"symbol": symbol, "outcome": "error", "reason": f"submit raised: {exc}",
                "trade_id": trade_id}

    # 6. record submission result (fill metrics captured later in reconciliation)
    sub = fill_recorder.record_submission(db, trade_id, resp, planned_entry=entry)
    if sub.get("was_rejected"):
        return {"symbol": symbol, "outcome": "error", "reason": "broker rejected/errored",
                "resp": resp, "trade_id": trade_id}
    return {"symbol": symbol, "outcome": "placed", "trade_id": trade_id,
            "broker_order_id": sub.get("broker_order_id"), "shares": shares,
            "risk_pct": decision.risk_pct, "notional": decision.notional}


def reconcile_open_fills(db, alpaca, *, account_type: str = "algo") -> int:
    """Sweep open algo trades whose entry hasn't been marked filled yet and pull
    the broker fill (called from the monitor loop). Returns count reconciled."""
    n = 0
    for t in db.get_open_algo_trades(account_type):
        if t.get("fill_price") is not None or not t.get("broker_order_id"):
            continue
        order = alpaca.get_order(t["broker_order_id"])
        if not order:
            continue
        fields = fill_recorder.record_open_fill(
            db, t["id"], order, planned_entry=t.get("entry_price"),
            requested_qty=t.get("shares"), submitted_at=t.get("submitted_at"))
        if fields.get("fill_price") is not None:
            n += 1
    return n
