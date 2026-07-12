"""
B3 risk state: the persistent daily-loss halt and drawdown kill-switch.

One row per account in the `risk_state` table. Everything here FAILS SAFE: if we
cannot read account equity, callers treat the account as halted (no new orders).
The halt flag is PERSISTED, so a crash-restart cannot resume trading while a
limit is breached.

Thresholds (from config['risk']), both evaluated on EQUITY (so unrealized losses
count):
  daily_loss_limit_pct  (e.g. -2.0): halt NEW opens when equity has fallen this
      far below the day's STARTING equity. Lifts on the next ET-day roll.
  drawdown_kill_pct     (e.g. -10.0): halt ALL opens when equity has fallen this
      far below the all-time equity HIGH-WATER MARK. PERSISTS until manual clear().
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional


def _now_et() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        return datetime.now(timezone.utc) - timedelta(hours=4)


def _today_et() -> str:
    return _now_et().date().isoformat()


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _limits(config: dict[str, Any]) -> dict[str, float]:
    r = (config or {}).get("risk", {}) or {}
    return {
        "daily_loss_limit_pct": float(r.get("daily_loss_limit_pct", -2.0)),
        "drawdown_kill_pct": float(r.get("drawdown_kill_pct", -10.0)),
    }


def _pct(now: float, base: float) -> Optional[float]:
    if not base:
        return None
    return (now - base) / base * 100.0


def refresh(db, account_type: str, equity: Optional[float], config: dict[str, Any]) -> dict[str, Any]:
    """Roll the day baseline + high-water mark from a fresh equity reading, then
    evaluate the halt thresholds. Returns the resulting risk_state row.

    When equity is None (broker read failed) we do NOT advance the baseline and
    do NOT clear any halt -- state is left as-is (fail safe)."""
    st = db.get_risk_state(account_type) or {}
    if equity is None:
        return st
    equity = float(equity)
    today = _today_et()
    hwm = max(float(st.get("equity_high_water_mark") or 0.0), equity)
    if st.get("day_key") != today:
        # New ET day: fresh baseline. A DAILY-LOSS halt lifts here; a DRAWDOWN
        # kill does NOT (it persists until manual clear()).
        fields: dict[str, Any] = dict(day_key=today, day_start_equity=equity,
                                      realized_pnl_today=0.0, equity_high_water_mark=hwm)
        if st.get("halted") and st.get("halt_reason") == "daily_loss":
            fields.update(halted=0, halt_reason=None, halted_at=None)
        db.upsert_risk_state(account_type, **fields)
    else:
        db.upsert_risk_state(account_type, equity_high_water_mark=hwm)
    return check_and_trip(db, account_type, equity, config)


def check_and_trip(db, account_type: str, equity: Optional[float],
                   config: dict[str, Any]) -> dict[str, Any]:
    """Evaluate daily-loss and drawdown thresholds; trip (persist) a halt if
    breached. NEVER auto-clears a halt -- clearing is manual or the day roll."""
    st = db.get_risk_state(account_type) or {}
    if equity is None:
        return st
    equity = float(equity)
    lim = _limits(config)
    day_start = float(st.get("day_start_equity") or equity)
    hwm = float(st.get("equity_high_water_mark") or equity)
    daily = _pct(equity, day_start)
    draw = _pct(equity, hwm)
    reason = None
    if draw is not None and draw <= lim["drawdown_kill_pct"]:
        reason = "drawdown"
    elif daily is not None and daily <= lim["daily_loss_limit_pct"]:
        reason = "daily_loss"
    if reason and not st.get("halted"):
        db.upsert_risk_state(account_type, halted=1, halt_reason=reason, halted_at=_iso())
    return db.get_risk_state(account_type) or {}


def is_halted(db, account_type: str) -> bool:
    st = db.get_risk_state(account_type)
    return bool(st and st.get("halted"))


def trip(db, account_type: str, reason: str = "manual") -> None:
    db.upsert_risk_state(account_type, halted=1, halt_reason=reason, halted_at=_iso())


def clear(db, account_type: str) -> None:
    """Manually lift a halt (operator action). A drawdown kill only lifts here."""
    db.upsert_risk_state(account_type, halted=0, halt_reason=None, halted_at=None)


def status(db, account_type: str, equity: Optional[float], config: dict[str, Any]) -> dict[str, Any]:
    """Read-only snapshot for the risk panel (no state change)."""
    st = db.get_risk_state(account_type) or {}
    lim = _limits(config)
    day_start = st.get("day_start_equity")
    hwm = st.get("equity_high_water_mark")
    daily = _pct(float(equity), float(day_start)) if equity and day_start else None
    draw = _pct(float(equity), float(hwm)) if equity and hwm else None
    return {
        "account_type": account_type,
        "halted": bool(st.get("halted")),
        "halt_reason": st.get("halt_reason"),
        "halted_at": st.get("halted_at"),
        "equity": equity,
        "day_start_equity": day_start,
        "equity_high_water_mark": hwm,
        "daily_pnl_pct": round(daily, 2) if daily is not None else None,
        "drawdown_pct": round(draw, 2) if draw is not None else None,
        "daily_loss_limit_pct": lim["daily_loss_limit_pct"],
        "drawdown_kill_pct": lim["drawdown_kill_pct"],
    }
