"""
Addendum 2 cross-cutting A -- sector trickle-down ("early to the pop").

Sector strength leads the small caps in that sector. We already compute weekly
sector bias + RS vs SPY for the 11 SPDRs (main-spec Lane 4, mtf_bias panel) --
this pipes it DOWNWARD onto the small-cap tape:

  sector_heat_score = bias(bull=1/neutral=0/bear=-1)
                    + RS-vs-SPY percentile across the 11 sectors
                    + normalized count of sub-$5 names in the sector triggering today

  sector_early = the sector ETF turned bullish recently (fresh flip) AND is not yet
                 extended (mid-caps haven't broken out) AND small-cap trigger count
                 is rising week-over-week. Any trigger in such a sector gets +10 and
                 a SECTOR EARLY chip -- catching the pop before the crowd.

The WoW trigger-trend component accrues: it needs ~8 sessions of history before it
can fire, so sector_early stays False until then (honest, not faked).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from src.database import Database

HEAT_KEY = "sc:sector_heat"
HIST_KEY = "sc:sector_trigger_hist"
PANEL_KEY = "market_bias:panel"
_NOT_EXTENDED_MAX = 8.0   # dist_20w_pct below this = move still young

# Finnhub finnhubIndustry -> SPDR sector, keyword rules (substring, first match wins)
_INDUSTRY_RULES: list[tuple[tuple[str, ...], str]] = [
    # health/biotech FIRST: "biotechnology" contains "technology", so XLV must win
    (("pharma", "biotech", "health", "medical", "life science", "drug", "hospital",
      "therapeut"), "XLV"),
    (("semiconduct", "technology", "software", "hardware", "electronic", "internet",
      "it services", "computer"), "XLK"),
    (("bank", "insurance", "financial", "capital market", "asset manage", "mortgage",
      "brokerage", "credit"), "XLF"),
    (("oil", "gas", "energy", "petroleum", "coal", "drilling"), "XLE"),
    (("aerospace", "defense", "machinery", "industrial", "airline", "transport",
      "engineering", "electrical equipment", "logistics", "railroad"), "XLI"),
    (("chemical", "metal", "mining", "materials", "steel", "paper", "forest", "gold"), "XLB"),
    (("consumer product", "retail", "apparel", "automobile", "auto ", "leisure", "hotel",
      "restaurant", "textile", "luxury", "homebuild", "e-commerce", "gaming", "casino"), "XLY"),
    (("food", "beverage", "tobacco", "household", "staple", "grocery", "agricult"), "XLP"),
    (("utilit", "power", "water util"), "XLU"),
    (("real estate", "reit"), "XLRE"),
    (("media", "telecom", "communication", "entertainment", "publishing", "advertis",
      "broadcast"), "XLC"),
]


def sector_to_spdr(sector_name: Optional[str]) -> Optional[str]:
    s = (sector_name or "").lower()
    if not s:
        return None
    for keys, spdr in _INDUSTRY_RULES:
        if any(k in s for k in keys):
            return spdr
    return None


def compute_sector_heat(db: Database, triggers: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Sector-heat map (per SPDR) from the cached bias panel + today's triggers.
    Persists a rolling trigger-count history for the WoW component, and the heat
    map itself under HEAT_KEY for the page's sector strip."""
    panel = (db.cache_get(PANEL_KEY) or {}).get("payload") or {}
    sectors = {r["symbol"]: r for r in panel.get("sectors", [])}
    if not sectors:
        return {}

    counts: dict[str, int] = {}
    for t in triggers:
        spdr = sector_to_spdr(t.get("sector_name"))
        if spdr:
            counts[spdr] = counts.get(spdr, 0) + 1

    # RS-vs-SPY percentile across the sectors present
    rs_ranked = sorted(sectors.items(), key=lambda kv: (kv[1].get("rs_vs_spy") or 0))
    n = len(rs_ranked)
    rs_pct = {sym: (i / (n - 1) if n > 1 else 0.5) for i, (sym, _) in enumerate(rs_ranked)}
    maxc = max(counts.values()) if counts else 0

    # roll the trigger-count history forward (dedupe today, keep last 14 days)
    today = datetime.now(timezone.utc).date().isoformat()
    hist = list((db.cache_get(HIST_KEY) or {}).get("payload") or [])
    hist = [h for h in hist if h.get("date") != today] + [{"date": today, "counts": counts}]
    hist = hist[-14:]
    db.cache_put(HIST_KEY, hist)

    def wow_rising(spdr: str) -> Optional[bool]:
        ser = [h["counts"].get(spdr, 0) for h in hist]
        if len(ser) < 8:
            return None    # still accruing
        return (sum(ser[-5:]) / 5) > (sum(ser[-10:-5]) / 5)

    out: dict[str, dict[str, Any]] = {}
    for spdr, r in sectors.items():
        bias_score = {"bullish": 1, "neutral": 0, "bearish": -1}.get(r.get("bias"), 0)
        tc = counts.get(spdr, 0)
        heat = round(bias_score + rs_pct.get(spdr, 0.5) + (tc / maxc if maxc else 0), 3)
        wr = wow_rising(spdr)
        not_extended = r.get("dist_20w_pct") is not None and r["dist_20w_pct"] < _NOT_EXTENDED_MAX
        early = bool(r.get("recently_bull") and not_extended and wr is True)
        out[spdr] = {
            "spdr": spdr, "bias": r.get("bias"), "rs_vs_spy": r.get("rs_vs_spy"),
            "rs_pctile": round(rs_pct.get(spdr, 0.5), 2), "trigger_count": tc,
            "dist_20w_pct": r.get("dist_20w_pct"), "recently_bull": r.get("recently_bull"),
            "wow_rising": wr, "heat_score": heat, "sector_early": early,
        }
    db.cache_put(HEAT_KEY, {"as_of": _iso_now(), "sectors": out})
    return out


def sector_early_spdrs(heat: dict[str, dict[str, Any]]) -> set[str]:
    return {s for s, o in heat.items() if o.get("sector_early")}


def is_sector_early(heat: dict[str, dict[str, Any]], sector_name: Optional[str]) -> bool:
    spdr = sector_to_spdr(sector_name)
    return bool(spdr and heat.get(spdr, {}).get("sector_early"))


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()
