"""
Market overview for the expanded Market Regime panel.

Presentation of free/existing data: indices (SPY/QQQ/IWM) + VIX via yfinance, a
breadth proxy computed from the sector rankings we already store, the economic
calendar (static forward schedule from config -- these dates are set in
advance), an earnings calendar for names currently held, and recent market news
headlines. The heavy bits (news, earnings) are cached so the dashboard poll
stays cheap.

Tuned to the server's yfinance (1.5.1): news title lives under item['content'],
and earnings come from Ticker.calendar['Earnings Date'] (get_earnings_dates
needs lxml, which isn't installed).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import yfinance as yf

from src import bias_strip

_CACHE: dict[str, dict[str, Any]] = {}

# Fallback economic schedule (macro dates are set in advance). Overridable via
# config.market_calendar.economic. Approximate -- edit in config to refine.
_DEFAULT_ECONOMIC = [
    {"date": "2026-07-14", "event": "CPI (June)", "importance": "high"},
    {"date": "2026-07-29", "event": "FOMC rate decision", "importance": "high"},
    {"date": "2026-08-07", "event": "Jobs report (July)", "importance": "high"},
    {"date": "2026-08-12", "event": "CPI (July)", "importance": "high"},
    {"date": "2026-09-04", "event": "Jobs report (August)", "importance": "high"},
    {"date": "2026-09-11", "event": "CPI (August)", "importance": "high"},
    {"date": "2026-09-16", "event": "FOMC rate decision", "importance": "high"},
    {"date": "2026-10-02", "event": "Jobs report (September)", "importance": "high"},
    {"date": "2026-10-13", "event": "CPI (September)", "importance": "high"},
    {"date": "2026-10-28", "event": "FOMC rate decision", "importance": "high"},
]


def _cached(key: str, ttl: int, fn):
    hit = _CACHE.get(key)
    if hit and time.time() - hit["ts"] < ttl:
        return hit["v"]
    try:
        v = fn()
    except Exception:
        v = None
    _CACHE[key] = {"ts": time.time(), "v": v}
    return v


def _vix() -> dict[str, Any] | None:
    def f():
        df = yf.Ticker("^VIX").history(period="7d", interval="1d")
        if df is None or df.empty or len(df) < 2:
            return None
        lvl, prev = float(df["Close"].iloc[-1]), float(df["Close"].iloc[-2])
        state = ("calm" if lvl < 15 else "normal" if lvl < 20
                 else "elevated" if lvl < 30 else "high fear")
        return {"level": round(lvl, 2), "prev": round(prev, 2),
                "change": round(lvl - prev, 2), "state": state}
    return _cached("vix", 300, f)


def _breadth(sector_rankings) -> dict[str, Any] | None:
    """Proxy from the 11 sector ETFs: how many are green today. yfinance has no
    official NYSE advance/decline; this is a cheap, honest stand-in."""
    perfs = [r.get("perf_1d") for r in (sector_rankings or []) if r.get("perf_1d") is not None]
    if not perfs:
        return None
    up = sum(1 for p in perfs if p > 0)
    return {"advancers": up, "decliners": len(perfs) - up, "total": len(perfs),
            "pct_up": round(100 * up / len(perfs))}


def _economic(config) -> list[dict[str, Any]]:
    events = ((config.get("market_calendar") or {}).get("economic")) or _DEFAULT_ECONOMIC
    today = datetime.now(timezone.utc).date().isoformat()
    return sorted([e for e in events if str(e.get("date", "")) >= today],
                  key=lambda e: e["date"])[:6]


# Market news + earnings are sourced from the FINNHUB cache the rate-limited
# refresher populates (news_refresher.tick). We only READ the cache here -- never
# a synchronous Finnhub call in the request path -- so a Finnhub outage or rate
# limit can never slow or break a page load. The panels stay usable while the
# cache is reasonably fresh, then flip to "unavailable" (below the hard limit we
# still show last-good data through a transient hiccup; past it we stop pretending).
_NEWS_HARD_LIMIT = 60 * 60        # market news: show cached up to 60 min, then unavailable
_EARN_HARD_LIMIT = 36 * 3600      # earnings calendar: refreshed daily, tolerate 36h


def _finnhub_news(db, finnhub_enabled: bool) -> dict[str, Any]:
    if db is None:
        return {"items": [], "available": False, "reason": "no-db"}
    hit = db.cache_get("news:market")
    if not hit or not hit.get("payload"):
        return {"items": [], "available": False,
                "reason": "disabled" if not finnhub_enabled else "refreshing"}
    age = hit.get("age_seconds")
    if age is not None and age > _NEWS_HARD_LIMIT:
        return {"items": [], "available": False, "reason": "unavailable",
                "fetched_at": hit.get("fetched_at")}
    items = [{"title": it.get("headline"), "provider": it.get("source"), "url": it.get("url")}
             for it in (hit["payload"] or [])[:8] if it.get("headline")]
    return {"items": items, "available": bool(items), "fetched_at": hit.get("fetched_at"),
            "reason": "empty" if not items else None}


def _finnhub_earnings(db, held_symbols: list[str], finnhub_enabled: bool,
                      days: int = 30) -> dict[str, Any]:
    if db is None:
        return {"items": [], "available": False, "reason": "no-db"}
    hit = db.cache_get("earnings:calendar")
    if not hit or not hit.get("payload"):
        return {"items": [], "available": False,
                "reason": "disabled" if not finnhub_enabled else "refreshing"}
    age = hit.get("age_seconds")
    if age is not None and age > _EARN_HARD_LIMIT:
        return {"items": [], "available": False, "reason": "unavailable"}
    held = {s.upper() for s in (held_symbols or [])}
    today = datetime.now(timezone.utc).date()
    out = []
    for e in (hit["payload"] or {}).get("earningsCalendar", []):
        sym = str(e.get("symbol", "")).upper()
        if held and sym not in held:            # "what's coming" = names you hold
            continue
        try:
            d = datetime.fromisoformat(str(e.get("date", ""))).date()
        except (TypeError, ValueError):
            continue
        if 0 <= (d - today).days <= days:
            out.append({"symbol": sym, "date": e.get("date")})
    out.sort(key=lambda x: x["date"])
    return {"items": out, "available": True}     # available even if no held name reports soon


def build(alpaca, sector_rankings, config, held_symbols,
          db=None, finnhub_enabled: bool = False) -> dict[str, Any]:
    news = _finnhub_news(db, finnhub_enabled)
    earn = _finnhub_earnings(db, held_symbols, finnhub_enabled)
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "indices": bias_strip.build(alpaca, ["SPY", "QQQ", "IWM"]),
        "vix": _vix(),
        "breadth": _breadth(sector_rankings),
        "economic": _economic(config),
        "earnings": earn["items"],
        "earnings_available": earn["available"],
        "news": news["items"],
        "news_available": news["available"],
        "news_reason": news.get("reason"),
        "news_fetched_at": news.get("fetched_at"),
        "finnhub_enabled": finnhub_enabled,
    }
