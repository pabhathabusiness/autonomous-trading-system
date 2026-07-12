"""
Alpaca live-data client (Phase 1 backbone).

AUTHORITATIVE SOURCE FOR: live + intraday price/volume across the universe --
real-time last trades and 15m/1h intraday bars (4h resampled from 1h). Free
tier is the IEX feed (real-time, but a single venue -- last print can lag on
thin low-float names, so every value we surface carries a bar-age stamp).

Data-source discipline (do NOT violate):
  * Alpaca  -> live intraday bars/quotes for the scan engine (this module).
  * yfinance -> weekly/monthly bars + fundamentals + float (NOT live intraday).
  * Robinhood -> watchlist quotes + options + execution (NOT scan data).
Two live sources may be shown side-by-side as a labelled cross-check, but are
never blended into one number.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd
import requests

from src import execution_guard, risk_gate

logger = logging.getLogger(__name__)

# Alpaca REST timeframe tokens
_TF = {"15m": "15Min", "1h": "1Hour", "1d": "1Day"}


def _parse_ts(ts: str) -> Optional[datetime]:
    """Parse Alpaca RFC3339 (nanosecond) timestamps robustly."""
    if not ts:
        return None
    try:
        s = ts.replace("Z", "+00:00")
        # trim fractional seconds to microseconds (Python max) if present
        if "." in s:
            head, frac = s.split(".", 1)
            tzpart = ""
            for marker in ("+", "-"):
                if marker in frac:
                    frac, tzpart = frac.split(marker, 1)
                    tzpart = marker + tzpart
                    break
            frac = frac[:6]
            s = f"{head}.{frac}{tzpart}"
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _age_seconds(ts: Optional[datetime]) -> Optional[float]:
    if ts is None:
        return None
    return round((datetime.now(timezone.utc) - ts).total_seconds(), 1)


class AlpacaClient:
    def __init__(self, config: dict[str, Any]):
        self._config = config
        cfg = config.get("alpaca", {})
        self.key = cfg.get("alpaca_key", "")
        self.secret = cfg.get("alpaca_secret", "")
        self.data_url = cfg.get("data_url", "https://data.alpaca.markets").rstrip("/")
        self.paper_url = cfg.get("paper_url", "https://paper-api.alpaca.markets").rstrip("/")
        # Hard paper-only default: order placement is walled to the paper host.
        self.paper_only = bool(cfg.get("paper_only", True))
        self.feed = cfg.get("feed", "iex")
        self.enabled = bool(cfg.get("enabled") and self.key and self.secret
                            and not self.key.startswith("YOUR_"))
        self._session = requests.Session()
        self._session.headers.update({
            "APCA-API-KEY-ID": self.key,
            "APCA-API-SECRET-KEY": self.secret,
        })
        if self.enabled:
            logger.info("Alpaca live data ENABLED (feed=%s)", self.feed)
        else:
            logger.info("Alpaca disabled (no keys) -- live features run degraded")

    # ------------------------------------------------------------------ REST
    def _get(self, url: str, params: dict[str, Any]) -> Optional[dict[str, Any]]:
        try:
            r = self._session.get(url, params=params, timeout=10)
            if r.status_code != 200:
                logger.debug("Alpaca %s -> %s: %s", url, r.status_code, r.text[:160])
                return None
            return r.json()
        except requests.RequestException as exc:
            logger.debug("Alpaca request failed: %s", exc)
            return None

    @staticmethod
    def _batches(symbols: list[str], size: int = 100):
        for i in range(0, len(symbols), size):
            yield symbols[i:i + size]

    # -------------------------------------------------------------- live price
    def latest_prices(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        """{symbol: {price, timestamp, age_seconds}} from latest IEX trades.
        Every entry carries a bar-age stamp so stale prints never look live."""
        if not self.enabled or not symbols:
            return {}
        out: dict[str, dict[str, Any]] = {}
        for batch in self._batches(sorted(set(symbols))):
            data = self._get(f"{self.data_url}/v2/stocks/trades/latest",
                             {"symbols": ",".join(batch), "feed": self.feed})
            if not data:
                continue
            for sym, trade in (data.get("trades") or {}).items():
                ts = _parse_ts(trade.get("t"))
                out[sym] = {
                    "price": float(trade.get("p")) if trade.get("p") is not None else None,
                    "timestamp": trade.get("t"),
                    "age_seconds": _age_seconds(ts),
                    "source": "alpaca_iex",
                }
        return out

    # -------------------------------------------------------------- intraday bars
    def bars(self, symbols: list[str], timeframe: str, limit: int = 200,
             start: Optional[str] = None) -> dict[str, pd.DataFrame]:
        """OHLCV bars per symbol as DataFrames (index=UTC time)."""
        if not self.enabled or not symbols:
            return {}
        tf = _TF.get(timeframe, timeframe)
        out: dict[str, pd.DataFrame] = {}
        for batch in self._batches(sorted(set(symbols)), size=50):
            params = {
                "symbols": ",".join(batch), "timeframe": tf,
                "limit": limit * len(batch), "feed": self.feed, "adjustment": "raw",
            }
            if start:
                params["start"] = start
            data = self._get(f"{self.data_url}/v2/stocks/bars", params)
            if not data:
                continue
            for sym, rows in (data.get("bars") or {}).items():
                if not rows:
                    continue
                df = pd.DataFrame(rows).rename(columns={
                    "t": "time", "o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume"})
                df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
                df = df.dropna(subset=["time"]).set_index("time").sort_index()
                out[sym] = df[["Open", "High", "Low", "Close", "Volume"]]
        return out

    def bars_4h(self, symbol: str) -> pd.DataFrame:
        """4-hour bars resampled from 1-hour (Alpaca has no native 4h)."""
        one_h = self.bars([symbol], "1h", limit=400).get(symbol)
        if one_h is None or one_h.empty:
            return pd.DataFrame()
        agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
        return one_h.resample("4h").agg(agg).dropna()

    # -------------------------------------------------------------- paper account
    def account(self) -> Optional[dict[str, Any]]:
        if not self.enabled:
            return None
        return self._get(f"{self.paper_url}/v2/account", {})

    def positions(self) -> list[dict[str, Any]]:
        """Open positions on the paper account (read-only)."""
        if not self.enabled:
            return []
        data = self._get(f"{self.paper_url}/v2/positions", {})
        return data if isinstance(data, list) else []

    # ----------------------------------------------------------- order placement
    def _post(self, url: str, body: dict[str, Any]) -> Optional[dict[str, Any]]:
        try:
            r = self._session.post(url, json=body, timeout=10)
            if r.status_code not in (200, 201):
                logger.warning("Alpaca POST %s -> %s: %s", url, r.status_code, r.text[:200])
                return {"error": r.text[:200], "status_code": r.status_code}
            return r.json()
        except requests.RequestException as exc:
            logger.warning("Alpaca POST failed: %s", exc)
            return {"error": str(exc)}

    def submit_bracket_order(self, *, symbol: str, qty: int, side: str,
                             entry_price: float, stop_price: float, target_price: float,
                             account_type: str, risk_decision: Any,
                             client_order_id: Optional[str] = None,
                             time_in_force: str = "day",
                             order_type: str = "limit") -> dict[str, Any]:
        """Submit a broker-managed BRACKET order (entry + attached stop-loss +
        take-profit) on the Alpaca PAPER account. Alpaca manages the exits
        server-side, so a position closes at its level even if our monitor loop
        hiccups.

        THREE FAIL-CLOSED GATES run before any POST, and this method is the SOLE
        caller of the order POST, so no caller can bypass them:
          1. execution_guard.assert_paper_execution -- paper book + paper host.
          2. risk_gate.assert_trade_allowed -- an APPROVED RiskDecision bound to
             this exact symbol+qty (the 7 B3 controls). REQUIRED, never optional.
          3. `assert 'paper-api' in self.paper_url` -- literal paper-host guard,
             belt-and-suspenders to gate 1. NEVER REMOVE THIS ASSERT.
        `client_order_id` is a deterministic idempotency key so a retry after a
        POST timeout cannot create a duplicate real bracket.
        """
        # ---- GATE 1: paper-vs-real wall (raises RealMoneyGuardError => no order) ----
        execution_guard.assert_paper_execution(
            account_type=account_type, endpoint_url=self.paper_url, config=self._config)

        # ---- GATE 2: risk gate (raises RiskGateError => no order). Enforced HERE,
        #      the single order chokepoint, so the 7 controls can't be bypassed. ----
        risk_gate.assert_trade_allowed(risk_decision, symbol=symbol, qty=int(qty))

        if not self.enabled:
            return {"status": "disabled", "reason": "alpaca not enabled (no keys)"}

        body: dict[str, Any] = {
            "symbol": symbol,
            "qty": str(int(qty)),
            "side": side,                       # 'buy' (long) / 'sell' (short)
            "type": order_type,                 # 'limit' entry by default
            "time_in_force": time_in_force,
            "order_class": "bracket",
            "take_profit": {"limit_price": round(float(target_price), 2)},
            "stop_loss": {"stop_price": round(float(stop_price), 2)},
        }
        if order_type == "limit":
            body["limit_price"] = round(float(entry_price), 2)
        if client_order_id:
            body["client_order_id"] = client_order_id     # idempotency (dedupes retries)

        # ---- GATE 3: literal paper-host assertion, immediately before the POST.
        #      NEVER REMOVE. Guards against a config/variable drift that would
        #      point the POST at a non-paper host after gate 1 validated paper_url.
        assert "paper-api" in self.paper_url, (
            f"REFUSING TO TRADE: paper_url '{self.paper_url}' is not the Alpaca paper host")
        return self._post(f"{self.paper_url}/v2/orders", body) or {"error": "no response"}

    def get_order(self, order_id: str) -> Optional[dict[str, Any]]:
        """Fetch a placed order WITH its bracket legs (for fill reconciliation).
        Read-only, paper host. nested=true returns the stop/target child orders."""
        if not self.enabled:
            return None
        return self._get(f"{self.paper_url}/v2/orders/{order_id}", {"nested": "true"})

    def get_order_by_client_id(self, client_order_id: str) -> Optional[dict[str, Any]]:
        """Find an order by our deterministic client_order_id -- used to detect a
        POST-timeout ORPHAN (Alpaca accepted the bracket but our _post timed out).
        Lists recent orders (status=all, nested legs) and matches client-side so we
        don't depend on a single-order-by-client-id endpoint."""
        if not self.enabled:
            return None
        data = self._get(f"{self.paper_url}/v2/orders",
                         {"status": "all", "limit": 200, "nested": "true"})
        if not isinstance(data, list):
            return None
        for o in data:
            if o.get("client_order_id") == client_order_id:
                return o
        return None

    def account_equity(self) -> Optional[float]:
        """Current paper-account equity for position sizing / risk state. None if
        the read fails -- callers must treat None as 'do not trade' (fail closed)."""
        acct = self.account()
        if not acct:
            return None
        for k in ("equity", "portfolio_value", "last_equity", "cash"):
            v = acct.get(k)
            if v is not None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    continue
        return None
