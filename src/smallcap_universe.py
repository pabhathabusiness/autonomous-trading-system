"""
Addendum 2 -- small-cap universe builder (daily premarket screen + enrich).

Pipeline (rate-limit aware):
  1. candidate symbols  -- Finnhub /stock/symbol (US), filtered to common stock
     on NASDAQ/NYSE/AMEX, cached 7d (stable list).
  2. cheap price/vol screen -- yfinance batch daily bars -> keep $0.50-$5.00 with
     >= $500k 20d avg $-volume. This kills 95% of names with ZERO Finnhub calls.
  3. float filter + enrich (survivors only) -- profile2 (SO-proxy tier, cached 7d),
     filings (dilution forms), basic_financials (Quality-Value fundamentals, cached
     3d), company-news (48h catalyst). Deathwatch names are written to
     smallcap_deathwatch and EXCLUDED from the universe.

Everything the four lane engines need is gathered here ONCE per name per refresh
and stored (scalars as columns, the rich stuff in signals_json), so the lane
rubrics in smallcap_lanes.py are pure over a universe row -- no re-fetching.

Float is SO-proxy (Finnhub free tier returns shares-outstanding but not true
free-float, verified 2026-07-12) -- so_proxy=1 on every row, labeled in the UI.
Going-concern (deathwatch c) and the >100%/12mo dilution treadmill (deathwatch d)
are deferred: filing body text isn't on free tier and SO history has to accrue.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

from src.database import Database
from src.finnhub_client import FinnhubClient
from src import smallcap_signals as ss

logger = logging.getLogger(__name__)

PRICE_MIN, PRICE_MAX = 0.50, 5.00
MIN_DOLLAR_VOL = 500_000            # 20d avg, below this fills are fiction
FLOAT_CAP_M = 100.0                 # universe excludes float > 100M
_DILUTION_FORMS = ("S-3", "S-1", "424B", "ATM")
_ALLOWED_MICS = {"XNAS", "XNYS", "XASE", "ARCX", "BATS"}   # NASDAQ/NYSE/AMEX family
_PROFILE_TTL_S = 7 * 24 * 3600
_FIN_TTL_S = 3 * 24 * 3600
_SYMBOLS_TTL_S = 7 * 24 * 3600
_SYMBOLS_KEY = "sc:us_symbols"


# ---------------------------------------------------------------- pure helpers
def float_tier(so_m: Optional[float]) -> Optional[str]:
    """runner < 20M | low 20-30M | standard 30-100M | None (>100M or unknown =>
    excluded from the universe)."""
    if so_m is None:
        return None
    if so_m < 20:
        return "runner"
    if so_m < 30:
        return "low"
    if so_m <= FLOAT_CAP_M:
        return "standard"
    return None


def dilution_from_filings(filings: Optional[list[dict[str, Any]]]) -> tuple[int, list[str]]:
    """S-3 / S-1 shelf, 424B pricing, ATM in recent filings => dilution_risk."""
    if not filings:
        return 0, []
    hits = sorted({(f.get("form") or "").upper() for f in filings
                   if any((f.get("form") or "").upper().startswith(x) for x in _DILUTION_FORMS)})
    return (1 if hits else 0), hits


def catalyst_from_news(news: Optional[list[dict[str, Any]]], now_ts: float,
                       max_age_h: float = 48) -> Optional[dict[str, Any]]:
    """Most-recent headline within max_age_h -> {headline,url,source,age_h}."""
    if not news:
        return None
    best = None
    for n in news:
        ts = n.get("datetime")
        if not ts:
            continue
        age_h = (now_ts - ts) / 3600
        if age_h < 0 or age_h > max_age_h:
            continue
        if best is None or age_h < best["age_h"]:
            best = {"headline": n.get("headline"), "url": n.get("url"),
                    "source": n.get("source"), "age_h": round(age_h, 1)}
    return best


def _support_context(df: pd.DataFrame, price: float) -> dict[str, Any]:
    """Lane-2 'at a real level' + level quality: proximity to the 200d SMA or to a
    swing low that has held >= 2x (tested support), from daily bars alone."""
    close, low = df["Close"], df["Low"]
    out = {"dist_to_sma200_pct": None, "near_sma200": False, "tested_swing_low": False,
           "swing_low_touches": 0, "level_quality": 0.0, "at_real_level": False}
    if len(close) >= 200:
        sma200 = float(close.rolling(200).mean().iloc[-1])
        if sma200 > 0:
            d = (price - sma200) / sma200 * 100
            out["dist_to_sma200_pct"] = round(d, 1)
            out["near_sma200"] = abs(d) <= 3
    # swing lows over the last 80 sessions (local minima, +/-3 bar window)
    win = low.iloc[-80:].tolist()
    swings = [win[i] for i in range(3, len(win) - 3) if win[i] == min(win[i - 3:i + 4])]
    near = [s for s in swings if price > 0 and abs(s - price) / price <= 0.03]
    out["swing_low_touches"] = len(near)
    out["tested_swing_low"] = len(near) >= 2
    q = 0.0
    if out["near_sma200"]:
        q = max(q, 0.6)
    if out["tested_swing_low"]:
        q = max(q, 0.8 if len(near) >= 3 else 0.65)
    out["level_quality"] = round(q, 2)
    out["at_real_level"] = bool(out["near_sma200"] or out["tested_swing_low"])
    return out


def demand_trend_features(df: pd.DataFrame) -> dict[str, Any]:
    """OHLC inputs the lane rubrics need (SMA20/50/200 + slope, %off-60d-high,
    selling exhaustion, undercut-reclaim, recent-runner, prior-day close, and
    Lane-2 support-level context)."""
    if df is None or len(df) < 60 or "Open" not in df:
        return {}
    close, high, low, vol, opn = df["Close"], df["High"], df["Low"], df["Volume"], df["Open"]
    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    hi60 = float(high.iloc[-60:].max())
    c = float(close.iloc[-1])
    avg20v = float(vol.iloc[-20:].mean())
    reds = df[df["Close"] < df["Open"]].tail(3)
    exhaustion = (float(reds["Volume"].mean()) < 0.7 * avg20v) if (len(reds) and avg20v > 0) else None
    prior10_low = float(low.iloc[-11:-1].min())
    rng = float(high.iloc[-1] - low.iloc[-1])
    ret10 = (c / float(close.iloc[-11]) - 1) * 100 if len(close) > 11 else None
    feat = {
        "sma20": round(float(sma20.iloc[-1]), 4),
        "sma50": round(float(sma50.iloc[-1]), 4),
        "sma50_slope_up": bool(sma50.iloc[-1] > sma50.iloc[-6]),
        "above_sma20": bool(c > sma20.iloc[-1]),
        "above_sma50": bool(c > sma50.iloc[-1]),
        "pct_off_60d_high": round((c - hi60) / hi60 * 100, 1) if hi60 else None,
        "exhaustion": exhaustion,
        "upper_third_close": bool(c >= float(low.iloc[-1]) + 0.667 * rng) if rng > 0 else False,
        "undercut_reclaim": bool(float(low.iloc[-1]) < prior10_low and c > prior10_low),
        "reclaim_prior_high": bool(c > float(high.iloc[-2]) and c > float(opn.iloc[-1])),
        "above_prior_close": bool(c > float(close.iloc[-2])),
        "ret_10d_pct": round(ret10, 1) if ret10 is not None else None,
        "recent_runner": bool(ret10 is not None and ret10 > 50),
        "prior10_low": round(prior10_low, 4),
    }
    feat.update(_support_context(df, c))
    return feat


def value_fundamentals(metric: Optional[dict[str, Any]], so_m: Optional[float]) -> dict[str, Any]:
    """Raw Quality-Value inputs from Finnhub basic-financials. The lane engine
    (S3) applies the pass/fail rubric; a missing field there => disqualified (no
    proxies on a value thesis). revenueTTM is reconstructed from per-share * SO."""
    if not metric:
        return {}
    rps = metric.get("revenuePerShareTTM")
    return {
        "revenueTTM_musd": round(rps * so_m, 1) if (rps is not None and so_m) else None,
        "revenueGrowthYoY": metric.get("revenueGrowthTTMYoy") or metric.get("revenueGrowthQuarterlyYoy"),
        "revenueGrowth5Y": metric.get("revenueShareGrowth5Y"),
        "grossMarginTTM": metric.get("grossMarginTTM") or metric.get("grossMarginAnnual"),
        "netMarginTTM": metric.get("netProfitMarginTTM"),
        "operCashFlowPerShareTTM": metric.get("cashFlowPerShareTTM"),
        "cashPerShareQuarterly": metric.get("cashPerSharePerShareQuarterly"),
        "debtToEquity": metric.get("totalDebt/totalEquityQuarterly") or metric.get("longTermDebt/equityQuarterly"),
        "psTTM": metric.get("psTTM") or metric.get("psAnnual"),   # valuation vs sector peers
    }


# ---------------------------------------------------------------- cached I/O
def _cached(db: Database, key: str, ttl_s: int, fetch) -> Any:
    hit = db.cache_get(key)
    if hit and hit.get("age_seconds") is not None and hit["age_seconds"] < ttl_s:
        return hit["payload"]
    val = fetch()
    if val is not None:
        db.cache_put(key, val)
        return val
    return hit["payload"] if hit else None    # serve stale rather than nothing


def candidate_symbols(db: Database, fh: FinnhubClient) -> list[str]:
    """US common stock on NASDAQ/NYSE/AMEX, cached 7d. [] if Finnhub disabled."""
    raw = _cached(db, _SYMBOLS_KEY, _SYMBOLS_TTL_S, fh.us_symbols)
    if not raw:
        return []
    out = []
    for s in raw:
        if (s.get("type") or "").lower() not in ("common stock", "stock", ""):
            continue
        mic = (s.get("mic") or "").upper()
        if _ALLOWED_MICS and mic and mic not in _ALLOWED_MICS:
            continue
        sym = (s.get("symbol") or "").upper()
        if sym and "." not in sym and sym.isascii():
            out.append(sym)
    return sorted(set(out))


# ---------------------------------------------------------------- enrich one
def enrich_symbol(db: Database, fh: FinnhubClient, symbol: str,
                  df: Optional[pd.DataFrame] = None,
                  splits: Optional[pd.Series] = None) -> dict[str, Any]:
    """Screen + enrich one symbol. Returns {status, symbol, [row]}. status is one
    of: added | deathwatch | skip_price | skip_liquidity | skip_float | skip_data."""
    import yfinance as yf
    if df is None:
        tk = yf.Ticker(symbol)
        df = tk.history(period="15mo", interval="1d", auto_adjust=True)   # >200 bars for sma200
        splits = tk.splits if splits is None else splits

    sig = ss.compute_ohlc_signals(df)
    if not sig:
        return {"status": "skip_data", "symbol": symbol}
    price = sig["price"]
    if not (PRICE_MIN <= price <= PRICE_MAX):
        return {"status": "skip_price", "symbol": symbol, "price": price}
    if (sig["avg_dollar_vol_20d"] or 0) < MIN_DOLLAR_VOL:
        return {"status": "skip_liquidity", "symbol": symbol}

    # deathwatch FIRST (hard filter): OHLC criteria a/b/e. Re-check clears stale.
    dw = ss.deathwatch_ohlc(df, splits)
    if dw:
        db.upsert_smallcap_deathwatch(symbol, dw[0], dw[1])
        return {"status": "deathwatch", "symbol": symbol, "reason": dw[0]}
    if db.is_on_deathwatch(symbol):
        db.delete_smallcap_deathwatch(symbol)   # aged out of the criteria

    prof = _cached(db, f"sc:profile2:{symbol}", _PROFILE_TTL_S, lambda: fh.profile2(symbol)) or {}
    so_m = prof.get("shareOutstanding")
    tier = float_tier(so_m)
    if tier is None:
        return {"status": "skip_float", "symbol": symbol, "so": so_m}

    filings = _cached(db, f"sc:filings:{symbol}", _FIN_TTL_S, lambda: fh.filings(symbol, 180))
    dilution_risk, dil_forms = dilution_from_filings(filings)
    metric = (_cached(db, f"sc:fin:{symbol}", _FIN_TTL_S, lambda: fh.basic_financials(symbol)) or {}).get("metric", {})
    news = fh.company_news(symbol, days=2)
    now_ts = datetime.now(timezone.utc).timestamp()
    catalyst = catalyst_from_news(news, now_ts, 48)

    signals_blob = {
        "ohlc": sig,
        "demand_trend": demand_trend_features(df),
        "fundamentals": value_fundamentals(metric, so_m),
        "catalyst": catalyst,
        "reverse_split": ss.reverse_split_flags(splits),
        "dilution_forms": dil_forms,
    }
    row = {
        "symbol": symbol,
        "price": price,
        "exchange": prof.get("exchange"),
        "sector_name": prof.get("finnhubIndustry"),
        "float_shares": so_m,
        "so_proxy": 1,                               # never true free-float on free tier
        "float_tier": tier,
        "avg_dollar_vol_20d": sig["avg_dollar_vol_20d"],
        "rel_vol": sig["rel_vol"],
        "bb_percentile": sig["bb_percentile"],
        "daily_compression": sig["daily_compression"],
        "compression_extreme": sig["compression_extreme"],
        "squeeze_days": sig["squeeze_days"],
        "up_wow": sig["up_wow"],
        "consecutive_up_weeks": sig["consecutive_up_weeks"],
        "dilution_risk": dilution_risk,
        # premium on free tier -> stay NULL, page shows "unavailable"
        "upside_to_target_pct": None,
        "has_options": None, "options_liquid": None, "has_leaps": None,
        "signals_json": __import__("json").dumps(signals_blob),
    }
    db.upsert_smallcap_universe(row)
    return {"status": "added", "symbol": symbol, "tier": tier, "price": price,
            "dilution_risk": dilution_risk, "catalyst": bool(catalyst)}


# ---------------------------------------------------------------- full build
def build_universe(db: Database, fh: FinnhubClient, *, symbols: Optional[list[str]] = None,
                   batch: int = 120, max_enrich: Optional[int] = None) -> dict[str, Any]:
    """Full daily build. `symbols` overrides the Finnhub candidate list (tests
    pass a small list). Cheap yfinance batch price/vol screen first, then enrich
    survivors. Returns a status-count summary."""
    import yfinance as yf
    if not fh.enabled:
        logger.info("smallcap build skipped -- Finnhub disabled")
        return {"skipped": "finnhub_disabled"}

    cands = symbols or candidate_symbols(db, fh)
    counts: dict[str, int] = {}
    logger.info("smallcap build: %d candidates", len(cands))

    survivors: list[tuple[str, pd.DataFrame]] = []
    for i in range(0, len(cands), batch):
        chunk = cands[i:i + batch]
        try:
            data = yf.download(chunk, period="15mo", interval="1d", auto_adjust=True,
                               group_by="ticker", threads=True, progress=False)
        except Exception as exc:
            logger.debug("batch download failed: %s", exc)
            continue
        for sym in chunk:
            try:
                sub = data[sym] if len(chunk) > 1 else data
                sub = sub.dropna(how="all")
                if sub is None or sub.empty:
                    continue
                px = float(sub["Close"].iloc[-1])
                dvol = float((sub["Close"].iloc[-20:] * sub["Volume"].iloc[-20:]).mean())
                if PRICE_MIN <= px <= PRICE_MAX and dvol >= MIN_DOLLAR_VOL:
                    survivors.append((sym, sub))
            except Exception:
                continue

    counts["price_vol_survivors"] = len(survivors)
    if max_enrich:
        survivors = survivors[:max_enrich]
    for sym, sub in survivors:
        try:
            r = enrich_symbol(db, fh, sym, df=sub, splits=yf.Ticker(sym).splits)
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        except Exception as exc:
            logger.debug("enrich %s failed: %s", sym, exc)
            counts["error"] = counts.get("error", 0) + 1
    logger.info("smallcap build done: %s", counts)
    return counts
