"""
Addendum 4 — Finnhub-derived edges: news polarity classification (the live bug
fix), insider activity, fundamental trends, 52w range + beta. Pure functions over
already-fetched payloads; the enrichment layer calls them and stores the results
in signals_json so the lane families read them.

The single most important fix here: an `offering` or `going_concern` headline was
counting as a POSITIVE catalyst. A stock spiking on an offering is spiking DOWN.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# A4 3.1 taxonomy. Order matters: hard-negatives are checked first so an
# "offering" headline can never be mistaken for a positive catalyst.
_NEWS_RULES: list[tuple[str, float, tuple[str, ...]]] = [
    ("going_concern", -2.0, ("going concern", "substantial doubt", "chapter 11", "bankruptcy", "restructuring")),
    ("offering", -1.5, ("offering", "registered direct", "priced at", "at-the-market", " atm ", "warrant", "dilut", "private placement", "pricing of")),
    ("delisting", -1.5, ("deficiency", "non-compliance", "delisting", "notice of noncompliance")),
    ("dilution_risk", -1.0, ("reverse split", "reverse stock split")),
    ("earnings_miss", -0.8, ("misses", "lowers guidance", "withdraws guidance", "cuts guidance", "guidance cut")),
    ("regulatory_win", 1.0, ("fda approval", "clearance", "510(k)", "designation", "patent granted", "approved", "authorization")),
    ("contract_award", 1.0, ("contract", "awarded", "award", "purchase order", "partnership", "definitive agreement", "selected by", "wins")),
    ("earnings_beat", 0.9, ("beats", "exceeds", "record revenue", "raises guidance", "tops estimates")),
    ("insider_buy_news", 0.6, ("insider purchase", "director buys", "ceo buys", "insider buying")),
    ("analyst_upgrade", 0.5, ("upgrade", "initiated coverage", "raised to buy", "outperform", "price target raised")),
    ("product_launch", 0.4, ("launches", "unveils", "begins shipping", "introduces", "rollout")),
    ("neutral_pr", 0.0, ("conference", "presents at", "webcast", "to present", "will participate", "fireside")),
]

_MAJOR_WIRES = ("reuters", "bloomberg", "associated press", "dow jones", "the wall street journal")
_PR_WIRES = ("globenewswire", "prnewswire", "pr newswire", "business wire", "businesswire", "accesswire")


def classify_headline(headline: str) -> tuple[str, float]:
    h = (headline or "").lower()
    for typ, weight, keys in _NEWS_RULES:
        if any(k in h for k in keys):
            return typ, weight
    return "neutral_pr", 0.0


def source_quality(source: Optional[str]) -> float:
    s = (source or "").lower()
    if any(w in s for w in _MAJOR_WIRES):
        return 1.0
    if any(w in s for w in _PR_WIRES):
        return 0.5
    return 0.25


def classify_news(items: Optional[list[dict[str, Any]]], now_ts: float,
                  window_days: int = 7) -> dict[str, Any]:
    """Dominant classified catalyst over the window + hard flags + velocity.
    catalyst family reads `weight` (clamped >=0); negative weights become a
    composite penalty; going_concern is a hard pass."""
    out = {"weight": 0.0, "type": None, "going_concern": False, "offering": False,
           "source_q": 0.0, "count_window": 0, "headline": None}
    if not items:
        return out
    win = window_days * 86400
    best = None
    for it in items:
        ts = it.get("datetime") or it.get("time")
        age = (now_ts - ts) if ts else 0
        recent = (ts is None) or (0 <= age <= win)
        typ, w = classify_headline(it.get("headline") or it.get("title") or "")
        if typ == "going_concern":
            out["going_concern"] = True
        if typ == "offering":
            out["offering"] = True
        if not recent:
            continue
        out["count_window"] += 1
        # dominant = largest magnitude (a -1.5 offering must beat a +0.4 product PR)
        if best is None or abs(w) > abs(best[1]):
            best = (typ, w, it)
    if best:
        out["type"], out["weight"] = best[0], best[1]
        out["headline"] = best[2].get("headline") or best[2].get("title")
        out["source_q"] = source_quality(best[2].get("source"))
    return out


# ------------------------------------------------------------- insider (A4 P2)
_BUY_CODE = "P"                       # open-market purchase ONLY
_COMP_CODES = {"M", "A", "G"}         # option exercise / grant / gift -> NOT a vote


def insider_score(txns: Optional[list[dict[str, Any]]], asof: Optional[datetime] = None,
                  market_cap_m: Optional[float] = None) -> dict[str, Any]:
    """Open-market ('P') purchases only. Cluster = >=2 distinct insiders buying
    within a 30d window. Returns {score, cluster, net_dollars, buyers_distinct, ...}.

    P2 units fix: Finnhub `share` is the insider's TOTAL post-transaction holdings;
    `change` is the actual transaction size (signed). Use `change`. Guard: any
    single transaction whose dollar value exceeds 25% of market cap is a data
    error -> drop it + log (never let a bad row inflate the signal)."""
    asof = asof or datetime.now(timezone.utc)
    out = {"score": 0.0, "cluster": False, "buyers_distinct": 0, "net_dollars": 0.0,
           "net_shares": 0.0, "last_buy_days_ago": None, "heavy_selling": False,
           "dropped_rows": 0, "available": False}
    if not txns:
        return out                              # no filings -> family UNAVAILABLE (BUG-5)
    out["available"] = True
    cap_dollars = market_cap_m * 1e6 if market_cap_m else None
    buys, sells_dollars = [], 0.0
    for t in txns:
        code = (t.get("transactionCode") or "").upper()
        change = t.get("change") or 0          # transaction size (NOT `share` = holdings)
        price = t.get("transactionPrice") or 0
        if not change:
            continue
        dollars = abs(change) * price
        if cap_dollars and dollars > 0.25 * cap_dollars:
            logger.warning("insider txn $%.0f > 25%% mcap ($%.0f) for %s -- dropping as data error",
                           dollars, cap_dollars, t.get("name"))
            out["dropped_rows"] += 1
            continue
        try:
            d = datetime.fromisoformat(str(t.get("transactionDate") or t.get("filingDate") or "")[:10])
            d = d.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            d = None
        if code == _BUY_CODE and change > 0:
            buys.append({"name": t.get("name"), "dollars": dollars, "date": d,
                         "days_ago": (asof - d).days if d else 9999})
        elif code == "S":
            sells_dollars += dollars
    if buys:
        out["net_shares"] = sum(1 for _ in buys)
        out["net_dollars"] = round(sum(b["dollars"] for b in buys) - sells_dollars, 0)
        recent = [b for b in buys if b["days_ago"] <= 90]
        distinct = {b["name"] for b in recent if b["name"]}
        out["buyers_distinct"] = len(distinct)
        out["last_buy_days_ago"] = min((b["days_ago"] for b in buys), default=None)
        # cluster: >=2 distinct insiders buying within any 30d window
        by_name_recent = [b for b in recent]
        if len({b["name"] for b in by_name_recent if b["days_ago"] <= 30 and b["name"]}) >= 2:
            out["cluster"] = True
        big = any(b["dollars"] >= 50000 and b["days_ago"] <= 90 for b in buys)
        if out["cluster"]:
            out["score"] = 1.0
        elif big:
            out["score"] = 0.7
        elif out["net_dollars"] > 0:
            out["score"] = 0.4
    else:
        out["net_dollars"] = round(-sells_dollars, 0)
    if out["net_dollars"] < -100000:
        out["heavy_selling"] = True
    return out


# --------------------------------------------------- fundamental trends + 52w
def revenue_trend(series: Optional[dict[str, Any]]) -> Optional[str]:
    """From metric.series.quarterly.salesPerShare: accelerating if the last 3
    QoQ deltas are increasing; decelerating if decreasing; else stable."""
    q = ((series or {}).get("quarterly") or {})
    sps = q.get("salesPerShare") or q.get("revenuePerShare")
    if not sps or len(sps) < 4:
        return None
    vals = [p.get("v") for p in sps[-4:] if p.get("v") is not None]
    if len(vals) < 4:
        return None
    d = [vals[i + 1] - vals[i] for i in range(len(vals) - 1)]
    if d[-1] > d[-2] > d[-3] and d[-1] > 0:
        return "accelerating"
    if d[-1] < d[-2] < d[-3]:
        return "decelerating"
    return "stable"


def range52_beta(metric: Optional[dict[str, Any]], price: Optional[float]) -> dict[str, Any]:
    m = metric or {}
    hi, lo = m.get("52WeekHigh"), m.get("52WeekLow")
    out = {"beta": m.get("beta"), "pct_of_52w_range": None, "pct_from_52w_high": None}
    if hi and lo and price is not None and hi > lo:
        out["pct_of_52w_range"] = round((price - lo) / (hi - lo), 3)
        out["pct_from_52w_high"] = round((price - hi) / hi * 100, 1)
    return out
