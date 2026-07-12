"""
News refresher (addendum): ONE sequential job, piggybacked on the scheduler's
monitor tick. Never parallel bursts -- FinnhubClient itself spaces calls ~1s.

Refresh policy (addendum, verbatim):
  * general market news        -> every 5 min, always
  * earnings calendar          -> once daily
  * per-symbol company news    -> every 15 min, ONLY for symbols someone
    actually clicked in the last hour (lazy + TTL)
  * sector news                -> derived: merged company news of the sector's
    top ~5 holdings (hardcoded map), same lazy 15-min TTL

Routes NEVER call Finnhub -- they read the cache and register interest here.
News is display-only: nothing in this module touches grades or verdicts.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

MARKET_TTL = 5 * 60
SYMBOL_TTL = 15 * 60
EARNINGS_TTL = 24 * 3600
INTEREST_WINDOW = 3600  # only refresh symbols/sectors clicked in the last hour

# SPDR sector -> top ~5 holdings (changes rarely; hardcoded per addendum)
SECTOR_HOLDINGS: dict[str, list[str]] = {
    "XLK": ["AAPL", "MSFT", "NVDA", "AVGO", "ORCL"],
    "XLF": ["BRK.B", "JPM", "V", "MA", "BAC"],
    "XLV": ["LLY", "UNH", "JNJ", "ABBV", "MRK"],
    "XLY": ["AMZN", "TSLA", "HD", "MCD", "BKNG"],
    "XLP": ["PG", "COST", "WMT", "KO", "PEP"],
    "XLE": ["XOM", "CVX", "COP", "WMB", "EOG"],
    "XLI": ["GE", "CAT", "RTX", "UBER", "ETN"],
    "XLB": ["LIN", "SHW", "APD", "ECL", "FCX"],
    "XLU": ["NEE", "SO", "DUK", "CEG", "AEP"],
    "XLRE": ["PLD", "AMT", "EQIX", "WELL", "SPG"],
    "XLC": ["META", "GOOGL", "NFLX", "TMUS", "DIS"],
}

# in-memory interest registry: cache key -> last time a user asked for it
_interest: dict[str, float] = {}


def register_interest(kind: str, name: str) -> None:
    _interest[f"{kind}:{name.upper()}"] = time.time()


def _wanted(kind: str, name: str) -> bool:
    ts = _interest.get(f"{kind}:{name.upper()}")
    return bool(ts and time.time() - ts < INTEREST_WINDOW)


def _stale(db, key: str, ttl: int) -> bool:
    hit = db.cache_get(key)
    return hit is None or hit["age_seconds"] is None or hit["age_seconds"] > ttl


def _norm_items(raw: list[dict[str, Any]] | None, limit: int = 25) -> list[dict[str, Any]]:
    out, seen = [], set()
    for it in (raw or [])[: limit * 2]:
        headline = (it.get("headline") or "").strip()
        if not headline:
            continue
        h = hashlib.sha1(headline.lower().encode()).hexdigest()[:12]  # dedupe by headline hash
        if h in seen:
            continue
        seen.add(h)
        out.append({"headline": headline, "source": it.get("source"),
                    "url": it.get("url"), "datetime": it.get("datetime"),
                    "summary": (it.get("summary") or "")[:280], "hash": h})
        if len(out) >= limit:
            break
    return out


def tick(db, fh) -> int:
    """One sequential pass; returns the number of Finnhub calls made."""
    if not getattr(fh, "enabled", False):
        return 0
    calls = 0
    try:
        if _stale(db, "news:market", MARKET_TTL):
            raw = fh.market_news(); calls += 1
            if raw is not None:
                items = _norm_items(raw)
                db.cache_put("news:market", items)
                db.insert_news_items(items)                 # A7 append-only store
        if _stale(db, "earnings:calendar", EARNINGS_TTL):
            raw = fh.earnings_calendar(days_ahead=30); calls += 1
            if raw is not None:
                db.cache_put("earnings:calendar", raw)
        # lazy per-symbol company news
        for key, ts in list(_interest.items()):
            if time.time() - ts >= INTEREST_WINDOW:
                _interest.pop(key, None)
                continue
            kind, name = key.split(":", 1)
            if kind == "symbol" and _stale(db, f"news:symbol:{name}", SYMBOL_TTL):
                raw = fh.company_news(name); calls += 1
                if raw is not None:
                    items = _norm_items(raw, limit=15)
                    for it in items:
                        it["symbol"] = name
                    db.cache_put(f"news:symbol:{name}", items)
                    db.insert_news_items(items)             # A7 append-only store
            elif kind == "sector" and _stale(db, f"news:sector:{name}", SYMBOL_TTL):
                merged: list[dict[str, Any]] = []
                for sym in SECTOR_HOLDINGS.get(name, [])[:5]:
                    raw = fh.company_news(sym); calls += 1
                    for it in _norm_items(raw, limit=8):
                        it["holding"] = sym
                        merged.append(it)
                # dedupe across holdings by headline hash, newest first
                seen, dedup = set(), []
                for it in sorted(merged, key=lambda x: x.get("datetime") or 0, reverse=True):
                    if it["hash"] in seen:
                        continue
                    seen.add(it["hash"]); dedup.append(it)
                db.cache_put(f"news:sector:{name}", dedup[:20])
    except Exception:
        logger.exception("news_refresher tick failed")
    # A7: recompute news clusters over the append-only store (pure text math,
    # zero API cost) -- wrapped so a clustering error never breaks the refresh
    try:
        from src import news_cluster
        news_cluster.compute_clusters(db)
    except Exception:
        logger.exception("news cluster compute failed")
    if calls:
        logger.info("news_refresher: %d Finnhub calls this tick", calls)
    return calls
