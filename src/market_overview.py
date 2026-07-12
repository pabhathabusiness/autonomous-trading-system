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


def _earnings(symbols: list[str]) -> list[dict[str, Any]]:
    if not symbols:
        return []

    def f():
        out = []
        for sym in sorted(set(symbols))[:15]:
            try:
                cal = yf.Ticker(sym).calendar or {}
            except Exception:
                continue
            dates = cal.get("Earnings Date") or []
            if dates:
                d = min(dates)
                out.append({"symbol": sym,
                            "date": d.isoformat() if hasattr(d, "isoformat") else str(d)})
        out.sort(key=lambda e: e["date"])
        return out
    return _cached("earn:" + ",".join(sorted(set(symbols))), 6 * 3600, f) or []


def _news() -> list[dict[str, Any]]:
    def f():
        items = yf.Ticker("SPY").news or []
        out = []
        for it in items[:8]:
            c = it.get("content") or it
            title = c.get("title")
            if not title:
                continue
            out.append({
                "title": title,
                "provider": (c.get("provider") or {}).get("displayName"),
                "url": (c.get("canonicalUrl") or c.get("clickThroughUrl") or {}).get("url"),
                "time": c.get("pubDate") or c.get("displayTime"),
            })
        return out
    return _cached("news", 900, f) or []


def build(alpaca, sector_rankings, config, held_symbols) -> dict[str, Any]:
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "indices": bias_strip.build(alpaca, ["SPY", "QQQ", "IWM"]),
        "vix": _vix(),
        "breadth": _breadth(sector_rankings),
        "economic": _economic(config),
        "earnings": _earnings(held_symbols),
        "news": _news(),
    }
