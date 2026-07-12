"""
B3 risk gate: the seven fail-closed controls every autonomous Alpaca PAPER order
must pass BEFORE submission.

  evaluate(ctx) -> RiskDecision          computes the decision from a RiskContext
  assert_trade_allowed(decision, ...)    the CHOKEPOINT assertion, called INSIDE
                                         AlpacaClient.submit_bracket_order

submit_bracket_order is the sole caller of the order POST, so enforcing the gate
there makes it structurally impossible for ANY caller -- scheduler, API, test, or
future code -- to place an order without an APPROVED decision bound to that exact
symbol + qty.

Every control FAILS CLOSED: if an input needed to evaluate a control is missing
(no equity read, no ADV, unknown sector), that control FAILS and the trade is
refused. There is no "allow on doubt" path.

The controls:
  0. not_halted        -- daily-loss / drawdown kill-switch is not tripped
  1. position_sizing   -- valid risk-based size (equity, stop distance, >=1 share)
  2. max_open_risk     -- existing open risk + this trade <= max_open_risk_pct (5%)
  3. per_lane_cap      -- lane open notional + this trade <= per_lane_cap_pct (30%)
  4. sector_cap        -- open positions in this sector < max_positions_per_sector (3)
  5. liquidity         -- price floor, min ADV$, order participation <= max % of ADV
  6. earnings_proximity-- not within earnings_blackout_days of earnings; UNKNOWN
                          earnings date fails CLOSED (refuse)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


class RiskGateError(RuntimeError):
    """Raised when an order is not covered by an APPROVED risk decision."""


@dataclass
class RiskContext:
    account_type: str
    symbol: str
    equity: Optional[float]
    entry: float
    stop: float
    target: float
    shares: int
    sector: Optional[str]
    lane: Optional[str]
    config: dict
    # open-exposure aggregates from the DB (INCLUDE rows already submitted this
    # scan, so successive evaluations can't blow through the caps before fills).
    open_risk: float = 0.0
    sector_counts: dict = field(default_factory=dict)
    lane_notional: dict = field(default_factory=dict)
    halted: bool = False
    # liquidity inputs
    avg_dollar_vol: Optional[float] = None
    rel_vol: Optional[float] = None
    # B3 earnings guard. earnings_available: was the calendar SEARCHED? If False,
    # the fetch failed -> UNKNOWN -> fail closed. If True, days_to_earnings None
    # means "no upcoming earnings" -> safe. int means days to the next report.
    days_to_earnings: Optional[int] = None
    earnings_available: bool = False


@dataclass
class RiskDecision:
    approved: bool
    symbol: str
    shares: int
    reason: str
    checks: dict[str, bool]
    risk_amount: float = 0.0
    risk_pct: Optional[float] = None
    notional: float = 0.0


def _rc(config: dict) -> dict:
    return (config or {}).get("risk", {}) or {}


def evaluate(ctx: RiskContext) -> RiskDecision:
    r = _rc(ctx.config)
    checks: dict[str, bool] = {}
    fails: list[str] = []

    def check(name: str, ok: bool, why: str) -> None:
        checks[name] = bool(ok)
        if not ok:
            fails.append(f"{name}: {why}")

    # 0. halt gate (daily-loss / drawdown)
    check("not_halted", not ctx.halted, "account halted (daily-loss or drawdown)")

    # 1. valid risk-based position sizing
    risk_per_share = abs(ctx.entry - ctx.stop)
    valid_size = (ctx.equity is not None and ctx.equity > 0 and ctx.entry > 0
                  and risk_per_share > 0 and ctx.shares >= 1)
    check("position_sizing", valid_size, "no equity / bad stop / zero shares")
    risk_amount = risk_per_share * ctx.shares if valid_size else 0.0
    notional = ctx.entry * ctx.shares if valid_size else 0.0
    risk_pct = (risk_amount / ctx.equity * 100.0) if (valid_size and ctx.equity) else None

    # 2. max open risk 5% (existing open+working risk + THIS trade)
    max_open = float(r.get("max_open_risk_pct", 5.0))
    if ctx.equity and ctx.equity > 0 and valid_size:
        proj = (ctx.open_risk + risk_amount) / ctx.equity * 100.0
        check("max_open_risk", proj <= max_open,
              f"projected open risk {proj:.2f}% > {max_open}%")
    else:
        check("max_open_risk", False, "no equity / invalid size")

    # 3. per-lane cap 30% of equity, by NOTIONAL
    lane_cap = float(r.get("per_lane_cap_pct", 30.0))
    if ctx.equity and ctx.equity > 0 and valid_size:
        lane_now = float(ctx.lane_notional.get(ctx.lane or "none", 0.0))
        lane_proj = (lane_now + notional) / ctx.equity * 100.0
        check("per_lane_cap", lane_proj <= lane_cap,
              f"lane '{ctx.lane}' notional {lane_proj:.1f}% > {lane_cap}%")
    else:
        check("per_lane_cap", False, "no equity / invalid size")

    # 4. correlation cap: max N open positions per sector
    max_sec = int(r.get("max_positions_per_sector", 3))
    sec = ctx.sector or "Unknown"
    sec_now = int(ctx.sector_counts.get(sec, 0))
    check("sector_cap", sec_now < max_sec,
          f"sector '{sec}' already has {sec_now} (max {max_sec})")

    # 5. liquidity guard: price floor, min ADV$, order participation vs ADV
    min_price = float(r.get("liquidity_min_price", 0.20))
    min_dv = float(r.get("liquidity_min_dollar_vol", 300_000))
    max_part = float(r.get("liquidity_max_adv_participation_pct", 1.0))
    liq_ok = True
    why: list[str] = []
    if ctx.entry < min_price:
        liq_ok = False
        why.append(f"price {ctx.entry} < {min_price}")
    if ctx.avg_dollar_vol is None:
        liq_ok = False
        why.append("no ADV data")
    else:
        if ctx.avg_dollar_vol < min_dv:
            liq_ok = False
            why.append(f"ADV$ {ctx.avg_dollar_vol:.0f} < {min_dv:.0f}")
        part = (notional / ctx.avg_dollar_vol * 100.0) if ctx.avg_dollar_vol else 999.0
        if part > max_part:
            liq_ok = False
            why.append(f"participation {part:.2f}% > {max_part}%")
    check("liquidity", liq_ok, "; ".join(why) or "ok")

    # 6. earnings-proximity blackout. Distinguish (silent-substitution trap):
    #    - fetch FAILED (not earnings_available) -> UNKNOWN -> fail closed (refuse).
    #    - searched, NO upcoming earnings (days None but available) -> SAFE -> pass.
    #    - searched, earnings within the blackout window -> refuse (real blackout).
    blackout = int(r.get("earnings_blackout_days", 2))
    dte = ctx.days_to_earnings
    if not ctx.earnings_available:
        earnings_ok, why_e = False, "earnings unavailable (fetch failed) -- fail closed"
    elif dte is not None and dte <= blackout:
        earnings_ok, why_e = False, f"earnings in {dte}d <= {blackout}d blackout"
    else:
        earnings_ok, why_e = True, "clear"
    check("earnings_proximity", earnings_ok, why_e)

    approved = all(checks.values())
    reason = "approved" if approved else " | ".join(fails)
    return RiskDecision(
        approved=approved, symbol=ctx.symbol, shares=ctx.shares, reason=reason,
        checks=checks, risk_amount=round(risk_amount, 2),
        risk_pct=round(risk_pct, 2) if risk_pct is not None else None,
        notional=round(notional, 2))


def assert_trade_allowed(decision: Optional[RiskDecision], *, symbol: str, qty: int) -> None:
    """The chokepoint assertion, called inside submit_bracket_order. Fails CLOSED
    unless `decision` is an APPROVED RiskDecision bound to this exact symbol+qty."""
    if not isinstance(decision, RiskDecision):
        raise RiskGateError("no RiskDecision supplied -- order refused (fail closed)")
    if not decision.approved:
        raise RiskGateError(f"risk gate did not approve {symbol}: {decision.reason}")
    if decision.symbol != symbol or int(decision.shares) != int(qty):
        raise RiskGateError(
            f"risk decision does not match order "
            f"(decision {decision.symbol}x{decision.shares} vs order {symbol}x{qty}) -- refused")
