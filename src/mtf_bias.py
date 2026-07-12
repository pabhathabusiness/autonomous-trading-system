"""
Lane 4: multi-timeframe coherence + weekly market-bias panel.

ONE shared bias method (price vs 20EMA + EMA slope + HH/HL structure) runs on
every timeframe for every consumer -- per-symbol MTF reads and the market
panel alike -- so a "bullish" always means the same thing. Every result is
timestamped so stale-data divergence is detectable.

Coherence gate: a trade's direction must agree with its own band TF AND one TF
above (1-2 day band = 4h + daily; swing band = daily + weekly). Intraday
disagreement is allowed -- it's displayed, never blocked ("W↓ D↓ 4h↑ pullback
entry"). Thesis-TF conflicts are LOGGED with raw inputs to mtf_conflicts for
the 2-week review; regime mismatch costs -1.0 quality + a caution, never a
hard block (that must be earned via learnings.json, n >= 8).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd
import yfinance as yf

from src import indicators

logger = logging.getLogger(__name__)

ARROW = {"bullish": "↑", "bearish": "↓", "neutral": "·"}
PANEL_KEY, REGIME_KEY = "market_bias:panel", "market_bias:regime"
PANEL_TTL = 12 * 3600          # weekly job + daily label refresh -> refresh ~daily
INDEXES = ["SPY", "QQQ", "IWM", "DIA", "RSP"]
SPDRS = ["XLK", "XLF", "XLV", "XLY", "XLP", "XLE", "XLI", "XLB", "XLU", "XLRE", "XLC"]
MAG7 = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"]


def tf_bias(df: Optional[pd.DataFrame]) -> str:
    """THE shared bias method: price vs 20EMA + 20EMA slope + HH/HL structure.
    2-of-3 agreement wins; anything else is neutral."""
    if df is None or len(df) < 25:
        return "neutral"
    closes = df["Close"]
    price = float(closes.iloc[-1])
    ema20 = indicators.ema(closes, 20)
    ema20_prev = indicators.ema(closes.iloc[:-3], 20)
    struct = indicators.structure_bias(*indicators.find_pivots(df, 3))
    votes_up = sum([bool(ema20 and price > ema20),
                    bool(ema20 and ema20_prev and ema20 > ema20_prev),
                    struct == "BULLISH"])
    votes_dn = sum([bool(ema20 and price < ema20),
                    bool(ema20 and ema20_prev and ema20 < ema20_prev),
                    struct == "BEARISH"])
    if votes_up >= 2 and votes_up > votes_dn:
        return "bullish"
    if votes_dn >= 2 and votes_dn > votes_up:
        return "bearish"
    return "neutral"


def _frames(symbol: str) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    try:
        w = yf.Ticker(symbol).history(period="2y", interval="1wk", auto_adjust=True)
        d = yf.Ticker(symbol).history(period="1y", interval="1d", auto_adjust=True)
        h = yf.Ticker(symbol).history(period="60d", interval="1h", auto_adjust=True)
    except Exception:
        return out
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    if w is not None and not w.empty: out["weekly"] = w
    if d is not None and not d.empty: out["daily"] = d
    if h is not None and not h.empty:
        out["1h"] = h
        cols = [c for c in agg if c in h.columns]
        out["4h"] = h[cols].resample("4h").agg({c: agg[c] for c in cols}).dropna()
    return out


# band -> (band TF, the one above) per the coherence gate
_BAND_TFS = {"1-2 day": ("4h", "daily"), "intraday": ("4h", "daily")}
_DEFAULT_TFS = ("daily", "weekly")   # swing / position-style bands


def evaluate(symbol: str, direction: str, band: Optional[str]) -> dict[str, Any]:
    """Per-symbol MTF read + coherence verdict for one proposed trade."""
    frames = _frames(symbol)
    biases = {tf: tf_bias(frames.get(tf)) for tf in ("weekly", "daily", "4h", "1h")}
    band_tf, above_tf = _BAND_TFS.get((band or "").strip(), _DEFAULT_TFS)
    want = "bearish" if direction == "short" else "bullish"
    agree = lambda tf: biases.get(tf) in (want, "neutral")   # neutral permits, never confirms
    confirmed = biases.get(band_tf) == want or biases.get(above_tf) == want
    coherent = agree(band_tf) and agree(above_tf) and confirmed
    conflict = (biases.get(band_tf) not in (want, "neutral")
                or biases.get(above_tf) not in (want, "neutral"))
    label = " ".join(f"{'W' if tf == 'weekly' else 'D' if tf == 'daily' else tf}"
                     f"{ARROW[biases[tf]]}" for tf in ("weekly", "daily", "4h", "1h"))
    intraday_diverges = biases.get("1h") not in (want, "neutral") or biases.get("4h") not in (want, "neutral")
    if intraday_diverges and coherent:
        label += " (pullback entry)"   # intraday disagreement = fine, labeled
    return {"symbol": symbol, "direction": direction, "band": band,
            "band_tf": band_tf, "above_tf": above_tf, "biases": biases,
            "coherent": coherent, "conflict": conflict, "label": label,
            "computed_at": datetime.now(timezone.utc).isoformat()}


# ------------------------------------------------------------- market panel
def _rs_vs_spy(closes: pd.Series, spy_closes: pd.Series, weeks: int = 13) -> Optional[float]:
    try:
        r = indicators.roc(closes, weeks)
        rs = indicators.roc(spy_closes, weeks)
        return round(r - rs, 2) if (r is not None and rs is not None) else None
    except Exception:
        return None


def build_panel() -> dict[str, Any]:
    """Weekly bias for indexes + 11 SPDRs + Mag7, RS vs SPY, distance from the
    20w EMA, weekly squeeze on/off; rolled up to market_regime."""
    weekly: dict[str, pd.DataFrame] = {}
    for sym in INDEXES + SPDRS + MAG7:
        try:
            w = yf.Ticker(sym).history(period="2y", interval="1wk", auto_adjust=True)
            if w is not None and not w.empty:
                weekly[sym] = w
        except Exception:
            continue
    spy_closes = weekly.get("SPY", pd.DataFrame()).get("Close")
    rows: dict[str, dict[str, Any]] = {}
    for sym, w in weekly.items():
        closes = w["Close"]
        price = float(closes.iloc[-1])
        e20 = indicators.ema(closes, 20)
        bb = indicators.bollinger_bands(closes)
        rows[sym] = {
            "symbol": sym,
            "bias": tf_bias(w),
            "rs_vs_spy": None if sym == "SPY" else _rs_vs_spy(closes, spy_closes),
            "dist_20w_pct": round((price - e20) / e20 * 100, 2) if e20 else None,
            "weekly_squeeze": bool(bb.get("squeeze")),
            "price": round(price, 2),
        }
    mag7_bull = sum(1 for s in MAG7 if rows.get(s, {}).get("bias") == "bullish")
    spy_b = rows.get("SPY", {}).get("bias")
    qqq_b = rows.get("QQQ", {}).get("bias")
    if spy_b == "bullish" and qqq_b == "bullish" and mag7_bull >= 4:
        regime = "risk_on"
    elif spy_b == "bearish" and qqq_b == "bearish" and mag7_bull <= 2:
        regime = "risk_off"
    else:
        regime = "chop"
    return {"as_of": datetime.now(timezone.utc).isoformat(), "regime": regime,
            "mag7_bullish": mag7_bull,
            "indexes": [rows[s] for s in INDEXES if s in rows],
            "sectors": [rows[s] for s in SPDRS if s in rows],
            "mag7": [rows[s] for s in MAG7 if s in rows]}


def refresh_panel(db, force: bool = False) -> Optional[str]:
    """Refresh the cached panel if stale (~daily). Returns the regime."""
    hit = db.cache_get(PANEL_KEY)
    if not force and hit and hit["age_seconds"] is not None and hit["age_seconds"] < PANEL_TTL:
        return (hit["payload"] or {}).get("regime")
    panel = build_panel()
    db.cache_put(PANEL_KEY, panel)
    db.cache_put(REGIME_KEY, {"regime": panel["regime"], "as_of": panel["as_of"]})
    logger.info("market bias panel refreshed: regime=%s mag7_bullish=%s",
                panel["regime"], panel["mag7_bullish"])
    return panel["regime"]


def current_regime(db) -> Optional[str]:
    hit = db.cache_get(REGIME_KEY)
    return (hit["payload"] or {}).get("regime") if hit else None


def regime_mismatch(direction: str, regime: Optional[str]) -> bool:
    return (direction == "long" and regime == "risk_off") or \
           (direction == "short" and regime == "risk_on")


def apply_to_proposal(db, proposal: dict[str, Any],
                      analysis: Optional[dict[str, Any]] = None) -> None:
    """Stamp Lane-4 context onto a proposal dict IN PLACE, before insert:
    market_regime + mtf_alignment (+ rs_vs_spy from the analysis), the -1.0
    quality penalty + caution on regime mismatch (never a hard block), and a
    conflicts-table row whenever the thesis TF disagrees."""
    try:
        direction = proposal.get("direction") or \
            ("short" if proposal.get("strategy") == "downside" else "long")
        regime = current_regime(db)
        proposal["market_regime"] = regime
        if proposal.get("rs_vs_spy") is None and analysis:
            proposal["rs_vs_spy"] = analysis.get("rs_vs_spy")
        band = "1-2 day" if "day" in str(proposal.get("expected_timeframe") or "").lower() else "swing"
        ev = evaluate(proposal["symbol"], direction, band)
        proposal["mtf_alignment"] = ev["label"]
        if ev["conflict"]:
            db.insert_mtf_conflict({**ev, "strategy": proposal.get("strategy"),
                                    "note": "thesis-TF conflict at proposal time"})
        if regime_mismatch(direction, regime):
            proposal["quality_score"] = max(0.0, round((proposal.get("quality_score") or 0.0) - 1.0, 2))
            proposal["reasoning"] = (proposal.get("reasoning") or "") + \
                f" CAUTION: {direction} against {regime} regime (-1.0 quality; thesis caution, not a block)."
    except Exception:
        logger.exception("apply_to_proposal failed for %s", proposal.get("symbol"))
