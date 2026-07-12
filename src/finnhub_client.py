"""
Finnhub client (addendum): key lives in .env as FINNHUB_KEY, never in git and
never sent to the browser -- all calls are proxied through backend routes that
read a server-side cache. This module is the ONLY place that talks to Finnhub.

Rate budget (free tier ~60/min) is enforced here mechanically: every call goes
through _get() which sleeps so consecutive calls are >= ~1s apart, and the
refresher job is single-threaded/sequential by design. Disabled (no key) ->
every method returns None and the cache simply stays empty.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

_BASE = "https://finnhub.io/api/v1"
_MIN_SPACING = 1.1  # seconds between calls (sequential budget, addendum)


def _load_env_key() -> str:
    """FINNHUB_KEY from the environment, else from a repo-root .env file.
    Tiny parser on purpose -- no python-dotenv dependency."""
    key = os.environ.get("FINNHUB_KEY", "").strip()
    if key:
        return key
    env_path = Path(__file__).resolve().parent.parent / ".env"
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("FINNHUB_KEY=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


class FinnhubClient:
    def __init__(self) -> None:
        self._key = _load_env_key()
        self.enabled = bool(self._key)
        self._last_call = 0.0
        self._session = requests.Session()
        # GATE 1: per-endpoint call outcomes so a coverage report can tell a
        # RATE-LIMIT (429) apart from a genuine error or an empty result. Keyed by
        # endpoint path -> {"ok", "rate_limited", "error"}.
        self.call_stats: dict[str, dict[str, int]] = {}
        logger.info("Finnhub %s", "ENABLED" if self.enabled else "disabled (no FINNHUB_KEY in .env)")

    def _stat(self, path: str, outcome: str) -> None:
        d = self.call_stats.setdefault(path, {"ok": 0, "rate_limited": 0, "error": 0})
        d[outcome] = d.get(outcome, 0) + 1

    def reset_call_stats(self) -> None:
        self.call_stats = {}

    def _get(self, path: str, params: dict[str, Any]) -> Optional[Any]:
        if not self.enabled:
            return None
        wait = _MIN_SPACING - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.time()
        try:
            r = self._session.get(f"{_BASE}{path}", params={**params, "token": self._key}, timeout=10)
            if r.status_code == 429:
                logger.warning("Finnhub 429 (rate limit) on %s -- backing off this cycle", path)
                self._stat(path, "rate_limited")
                return None
            if r.status_code != 200:
                logger.debug("Finnhub %s -> %s", path, r.status_code)
                self._stat(path, "error")
                return None
            self._stat(path, "ok")
            return r.json()
        except requests.RequestException as exc:
            logger.debug("Finnhub request failed: %s", exc)
            self._stat(path, "error")
            return None

    # ---- endpoints used (addendum table) ----
    def market_news(self) -> Optional[list[dict[str, Any]]]:
        return self._get("/news", {"category": "general"})

    def company_news(self, symbol: str, days: int = 7) -> Optional[list[dict[str, Any]]]:
        to = date.today()
        return self._get("/company-news", {"symbol": symbol.upper(),
                                           "from": (to - timedelta(days=days)).isoformat(),
                                           "to": to.isoformat()})

    def earnings_calendar(self, days_ahead: int = 30) -> Optional[dict[str, Any]]:
        frm = date.today()
        return self._get("/calendar/earnings", {"from": frm.isoformat(),
                                                "to": (frm + timedelta(days=days_ahead)).isoformat()})

    def earnings_for_symbol(self, symbol: str, days_ahead: int = 45,
                            days_back: int = 5) -> Optional[dict[str, Any]]:
        """Per-symbol earnings calendar over a window around today. Returns the
        raw Finnhub payload ({'earningsCalendar': [...]}) or None on fetch failure
        -- so a rate-limit is distinguishable from a genuinely-empty calendar (GATE
        1 / B3 earnings guard). Fetch failure => days-to-earnings UNKNOWN => the
        risk gate fails closed."""
        frm = date.today() - timedelta(days=days_back)
        return self._get("/calendar/earnings",
                         {"symbol": symbol.upper(), "from": frm.isoformat(),
                          "to": (date.today() + timedelta(days=days_ahead)).isoformat()})

    # ---- Addendum 2 small-cap endpoints (free-tier verified 2026-07-12) ----
    def profile2(self, symbol: str) -> Optional[dict[str, Any]]:
        """Company profile: shareOutstanding (millions), marketCapitalization,
        finnhubIndustry, exchange, name. Free tier returns real shares-outstanding
        (true free-float is NOT available -> callers tier by SO and label SO-proxy)."""
        return self._get("/stock/profile2", {"symbol": symbol.upper()})

    def basic_financials(self, symbol: str) -> Optional[dict[str, Any]]:
        """{'metric': {...}, 'series': {...}}. Free tier is rich even for small
        names: margins, revenue growth, D/E, cash/rev per share -> Quality-Value."""
        return self._get("/stock/metric", {"symbol": symbol.upper(), "metric": "all"})

    def filings(self, symbol: str, days: int = 180) -> Optional[list[dict[str, Any]]]:
        """SEC filing METADATA (form, filedDate, reportUrl) -- free tier. Used to
        flag dilution risk by form type (S-3/424B/ATM). Body text is NOT included,
        so going-concern language is not checked here (deferred, by design)."""
        to = date.today()
        return self._get("/stock/filings", {"symbol": symbol.upper(),
                                            "from": (to - timedelta(days=days)).isoformat(),
                                            "to": to.isoformat()})

    def insider_transactions(self, symbol: str, days: int = 180) -> Optional[dict[str, Any]]:
        """Open-market + comp insider txns (free tier, A4 P2). Filter to code 'P'
        in the scorer. Returns {'data': [...], 'symbol': ..}."""
        to = date.today()
        return self._get("/stock/insider-transactions", {"symbol": symbol.upper(),
                         "from": (to - timedelta(days=days)).isoformat(), "to": to.isoformat()})

    def earnings_surprise(self, symbol: str) -> Optional[list[dict[str, Any]]]:
        """Actual vs estimate EPS history (free tier). beat_streak / avg_surprise."""
        return self._get("/stock/earnings", {"symbol": symbol.upper()})

    def recommendation(self, symbol: str) -> Optional[list[dict[str, Any]]]:
        """Analyst buy/hold/sell counts over time (free; price-target is premium)."""
        return self._get("/stock/recommendation", {"symbol": symbol.upper()})

    def peers(self, symbol: str) -> Optional[list[str]]:
        """Real peer set for relative valuation (free tier)."""
        return self._get("/stock/peers", {"symbol": symbol.upper()})

    def us_symbols(self) -> Optional[list[dict[str, Any]]]:
        """All US-listed symbols (reference data, free tier). Each item has
        symbol/type/mic/description; the universe builder filters to common
        stock on NASDAQ/NYSE/AMEX. Cached with a long TTL -- this list is stable."""
        return self._get("/stock/symbol", {"exchange": "US"})

    # NOTE: /stock/price-target and /stock/option-chain are PREMIUM (HTTP 403 on
    # free tier, probed 2026-07-12). Deliberately NOT implemented -- the page
    # renders those as "unavailable" chips rather than fabricating data.
