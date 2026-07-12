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
        logger.info("Finnhub %s", "ENABLED" if self.enabled else "disabled (no FINNHUB_KEY in .env)")

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
                return None
            if r.status_code != 200:
                logger.debug("Finnhub %s -> %s", path, r.status_code)
                return None
            return r.json()
        except requests.RequestException as exc:
            logger.debug("Finnhub request failed: %s", exc)
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

    def us_symbols(self) -> Optional[list[dict[str, Any]]]:
        """All US-listed symbols (reference data, free tier). Each item has
        symbol/type/mic/description; the universe builder filters to common
        stock on NASDAQ/NYSE/AMEX. Cached with a long TTL -- this list is stable."""
        return self._get("/stock/symbol", {"exchange": "US"})

    # NOTE: /stock/price-target and /stock/option-chain are PREMIUM (HTTP 403 on
    # free tier, probed 2026-07-12). Deliberately NOT implemented -- the page
    # renders those as "unavailable" chips rather than fabricating data.
