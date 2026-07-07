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
        cfg = config.get("alpaca", {})
        self.key = cfg.get("alpaca_key", "")
        self.secret = cfg.get("alpaca_secret", "")
        self.data_url = cfg.get("data_url", "https://data.alpaca.markets").rstrip("/")
        self.paper_url = cfg.get("paper_url", "https://paper-api.alpaca.markets").rstrip("/")
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
