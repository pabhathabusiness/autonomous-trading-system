"""
Addendum 7 — auto-cluster cached news by TRENDING keywords.

Pure text math over already-cached news -- ZERO new API calls. Runs every 15 min
over the last 24h of market + company news. Terms are scored by trending-ness
(today's rate vs a 30-day baseline), NOT raw count, so a genuinely emerging story
outranks evergreen boilerplate. Clusters map to the tickers/sectors named in them.

This is a CONTEXT/AWARENESS surface only. It never generates a trade or a verdict
(narrative is not an edge). Cluster volume feeds news_regime_tilt as a tiebreaker
only when the technical regime is 'chop' (Addendum 4 Part 9).
"""

from __future__ import annotations

import logging
import re
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)
CLUSTERS_KEY = "news:clusters"

# minimal stopword set (headline-appropriate) + finance boilerplate that trends
# for the wrong reasons
_STOP = set("""a an the of to in on for and or but with at by from as is are was were be been
being this that these those it its their his her they them we you your our i he she
new now more most will would can could may might shares stock stocks market inc corp
ltd co company companies report reports says said announces announced update updates
today week month year first second third quarter q1 q2 q3 q4 amid vs after before over
into out up down off per about which who what when where why how has have had not no
than then them”s us""".split())

# reverse of the SPDR top-holdings map (news_refresher.SECTOR_HOLDINGS) gives a
# best-effort ticker -> SPDR for the mega names; small names fall back to the
# smallcap_universe sector at call time.
_TICKER_SPDR = {
    "AAPL": "XLK", "MSFT": "XLK", "NVDA": "XLK", "AVGO": "XLK", "ORCL": "XLK",
    "JPM": "XLF", "V": "XLF", "MA": "XLF", "BAC": "XLF", "BRK.B": "XLF",
    "LLY": "XLV", "UNH": "XLV", "JNJ": "XLV", "ABBV": "XLV", "MRK": "XLV",
    "AMZN": "XLY", "TSLA": "XLY", "HD": "XLY", "MCD": "XLY", "BKNG": "XLY",
    "PG": "XLP", "COST": "XLP", "WMT": "XLP", "KO": "XLP", "PEP": "XLP",
    "XOM": "XLE", "CVX": "XLE", "COP": "XLE", "WMB": "XLE", "EOG": "XLE",
    "GE": "XLI", "CAT": "XLI", "RTX": "XLI", "UBER": "XLI", "ETN": "XLI",
    "META": "XLC", "GOOGL": "XLC", "NFLX": "XLC", "TMUS": "XLC", "DIS": "XLC",
}

_WORD = re.compile(r"[A-Za-z][A-Za-z'&-]{1,}")


def _terms(headline: str) -> set[str]:
    """Bigrams + trigrams of non-stopword tokens (deduped per headline so one
    headline can't inflate a term's count)."""
    toks = [w.lower() for w in _WORD.findall(headline or "")]
    # keep 2-char tokens (AI, EV, FDA, IPO, M&A all matter); _STOP handles noise
    toks = [t for t in toks if t not in _STOP and len(t) >= 2]
    grams = set()
    for n in (2, 3):
        for i in range(len(toks) - n + 1):
            grams.add(" ".join(toks[i:i + n]))
    return grams


def build_baseline(items_30d: Optional[list[dict[str, Any]]]) -> Counter:
    """30-day term counts, for the trending denominator."""
    base: Counter = Counter()
    for it in (items_30d or []):
        for term in _terms(it.get("headline") or it.get("title") or ""):
            base[term] += 1
    return base


def cluster_news(items_24h: list[dict[str, Any]], baseline: Counter, *,
                 min_count: int = 3, max_clusters: int = 8,
                 sector_lookup: Optional[dict[str, str]] = None) -> list[dict[str, Any]]:
    """Cluster the last 24h of news under trending terms.

    trend_score = count_24h / (baseline_30d / 30); require count_24h >= min_count
    (kills one-off noise). Each headline is assigned to its single highest-scoring
    qualifying term. Clusters carry the tickers named (item['symbol']/['related'])
    and the SPDR sectors of those tickers, ranked by mention count."""
    if not items_24h:
        return []
    # term -> list of item indexes
    term_items: dict[str, list[int]] = {}
    term_count: Counter = Counter()
    for i, it in enumerate(items_24h):
        for term in _terms(it.get("headline") or it.get("title") or ""):
            term_items.setdefault(term, []).append(i)
            term_count[term] += 1

    scored = []
    for term, cnt in term_count.items():
        if cnt < min_count:
            continue
        base_rate = (baseline.get(term, 0) / 30.0) or (1 / 30.0)   # unseen term => strong signal
        trend = cnt / base_rate
        scored.append((term, cnt, round(trend, 1)))
    scored.sort(key=lambda x: x[2], reverse=True)

    # assign each headline to its single best (highest-trend) qualifying term
    best_term_for_item: dict[int, tuple[str, float]] = {}
    for term, cnt, trend in scored:
        for i in term_items[term]:
            if i not in best_term_for_item or trend > best_term_for_item[i][1]:
                best_term_for_item[i] = (term, trend)

    lookup = {**_TICKER_SPDR, **(sector_lookup or {})}
    clusters = []
    for term, cnt, trend in scored[:max_clusters]:
        members = [i for i in term_items[term] if best_term_for_item.get(i, (None,))[0] == term]
        if len(members) < min_count:
            continue
        tickers = Counter()
        for i in members:
            sym = (items_24h[i].get("symbol") or items_24h[i].get("related") or "").upper()
            if sym:
                tickers[sym] += 1
        sectors = Counter()
        for sym, c in tickers.items():
            spdr = lookup.get(sym)
            if spdr:
                sectors[spdr] += c
        clusters.append({
            "term": term, "count": len(members), "trend_score": trend,
            "tickers": [t for t, _ in tickers.most_common(8)],
            "sectors": [s for s, _ in sectors.most_common(4)],
            "news_ids": [items_24h[i].get("hash") or items_24h[i].get("id") for i in members][:20],
            "sample": (items_24h[members[0]].get("headline") or items_24h[members[0]].get("title")),
        })
    return clusters


def compute_clusters(db, now_ts: Optional[float] = None) -> list[dict[str, Any]]:
    """Cluster the append-only news store (24h vs 30d baseline) and cache the
    result under CLUSTERS_KEY. Pure text math -- ZERO API calls. Safe no-op if the
    store is empty. Called from the news refresher every tick (cheap)."""
    now_ts = now_ts or time.time()
    try:
        items_24h = db.get_news_items(int(now_ts - 24 * 3600))
        if not items_24h:
            return []
        baseline = build_baseline(db.get_news_items(int(now_ts - 30 * 86400)))
        clusters = cluster_news(items_24h, baseline, min_count=3)
        db.cache_put(CLUSTERS_KEY, {"as_of": datetime.now(timezone.utc).isoformat(),
                                    "clusters": clusters, "regime_tilt": regime_tilt(clusters),
                                    "items_24h": len(items_24h)})
        return clusters
    except Exception:
        logger.exception("compute_clusters failed")
        return []


def regime_tilt(clusters: list[dict[str, Any]]) -> Optional[str]:
    """Soft risk-on/off tilt from cluster terms -- a TIEBREAKER only when the
    technical regime is 'chop' (A4 P9). Never overrides technicals."""
    RISK_OFF = ("recession", "selloff", "sell-off", "hawkish", "tightening", "crisis", "plunge", "crash", "war")
    RISK_ON = ("rally", "record high", "dovish", "rate cut", "cuts rates", "soft landing", "surge")
    off = sum(c["count"] for c in clusters if any(k in c["term"] for k in RISK_OFF))
    on = sum(c["count"] for c in clusters if any(k in c["term"] for k in RISK_ON))
    if off > on and off >= 3:
        return "risk_off"
    if on > off and on >= 3:
        return "risk_on"
    return None
