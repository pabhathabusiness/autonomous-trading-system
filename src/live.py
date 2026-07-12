"""
Live snapshot builder (Phase 1 backbone).

Takes the open simulated (paper) trades and prices them against Alpaca's live
IEX feed to produce the real-time layer the dashboard rides on:
  * live price + live unrealized P&L per open paper trade (direction-aware)
  * distance to the frozen stop / target (the plan, locked at entry)
  * relative strength vs SPY (simple session %, side-by-side -- never blended)
  * a bar-age stamp on every price so stale prints never look live

This is what powers the autonomous paper-trade book in the background: every
open trade is continuously marked to real prices. Resolution (win/loss) still
uses full-session highs/lows in paper_trader; this adds the *live* mark.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

# session-open cache so we don't refetch daily bars every 5s (open is fixed
# for the session); keyed by UTC date.
_open_cache: dict[str, dict[str, float]] = {}


def _session_opens(alpaca, symbols: list[str]) -> dict[str, float]:
    if not symbols:
        return {}
    today = datetime.now(timezone.utc).date().isoformat()
    cache = _open_cache.setdefault(today, {})
    missing = [s for s in symbols if s not in cache]
    if missing and alpaca.enabled:
        start = (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat()
        bars = alpaca.bars(missing, "1d", limit=8, start=start)
        for sym, df in bars.items():
            if df is not None and not df.empty:
                cache[sym] = float(df["Open"].iloc[-1])
    # prune old dates
    for d in list(_open_cache):
        if d != today:
            _open_cache.pop(d, None)
    return {s: cache[s] for s in symbols if s in cache}


def build_live_snapshot(db, alpaca) -> dict[str, Any]:
    open_trades = db.get_paper_trades(status="open")
    symbols = sorted({t["symbol"] for t in open_trades} | {"SPY"})

    prices = alpaca.latest_prices(symbols) if alpaca.enabled else {}
    opens = _session_opens(alpaca, symbols)

    def session_pct(sym: str) -> Optional[float]:
        live = prices.get(sym, {}).get("price")
        op = opens.get(sym)
        if live is None or not op:
            return None
        return round((live - op) / op * 100, 2)

    spy = prices.get("SPY", {})
    spy_pct = session_pct("SPY")

    trades: list[dict[str, Any]] = []
    for t in open_trades:
        info = prices.get(t["symbol"], {})
        lp = info.get("price")
        entry, stop, tgt = t["entry_price"], t["stop_loss"], t["target_price"]
        is_short = t.get("direction") == "short"

        live_pnl = None
        if lp and entry:
            live_pnl = round(((entry - lp) if is_short else (lp - entry)) / entry * 100, 2)
        name_pct = session_pct(t["symbol"])
        rs = round(name_pct - spy_pct, 2) if (name_pct is not None and spy_pct is not None) else None

        # dollar accounting (needs shares; legacy rows have none -> None)
        shares = t.get("shares")
        position_value = round(shares * lp, 2) if (shares and lp) else None
        live_pnl_usd = None
        if shares and lp and entry:
            live_pnl_usd = round(shares * ((entry - lp) if is_short else (lp - entry)), 2)
        days_held = None
        try:
            days_held = (datetime.now(timezone.utc) - datetime.fromisoformat(t["entry_date"])).days
        except (ValueError, TypeError):
            pass

        trades.append({
            "id": t["id"], "symbol": t["symbol"], "sector_name": t["sector_name"],
            "strategy": t["strategy"], "direction": t.get("direction", "long"),
            "confidence": t["confidence"],
            # frozen plan (locked at entry -- the discipline anchor)
            "entry_price": entry, "stop_loss": stop, "target_price": tgt,
            "entry_date": t["entry_date"], "days_held": days_held,
            "shares": shares,
            # live mark
            "live_price": lp,
            "age_seconds": info.get("age_seconds"),
            "live_pnl_pct": live_pnl,
            "live_pnl_usd": live_pnl_usd,
            "position_value": position_value,
            "dist_to_stop_pct": round((lp - stop) / lp * 100, 2) if lp else None,
            "dist_to_target_pct": round((tgt - lp) / lp * 100, 2) if lp else None,
            # relative strength (side-by-side, not blended)
            "name_session_pct": name_pct,
            "rs_vs_spy": rs,
        })

    # sort by biggest live gain first for a useful default view
    trades.sort(key=lambda x: (x["live_pnl_pct"] is not None, x["live_pnl_pct"] or -999), reverse=True)

    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "alpaca_enabled": alpaca.enabled,
        "spy": {"price": spy.get("price"), "session_pct": spy_pct, "age_seconds": spy.get("age_seconds")},
        "open_count": len(open_trades),
        "priced_count": sum(1 for t in trades if t["live_price"] is not None),
        "trades": trades,
    }
