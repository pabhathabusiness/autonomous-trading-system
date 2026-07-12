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
from datetime import date, datetime, timezone
from typing import Any, Optional

import pandas as pd

from src.database import Database
from src.finnhub_client import FinnhubClient
from src import smallcap_signals as ss
from src import smallcap_edges as edges

logger = logging.getLogger(__name__)

PRICE_MIN, PRICE_MAX = 0.20, 10.00  # A3 Part 2: four price tiers span $0.20-$10
MIN_DOLLAR_VOL = 300_000            # A3 1.2: lowered from 500k (was over-tight for cheap tiers)
FLOAT_CAP_M = 1000.0               # F3: universe ceiling 1B. Float is NEVER a build gate --
                                   # lanes carry their own float ceilings; float is a scored edge.
_DILUTION_FORMS = ("S-3", "S-1", "424B", "ATM")
_ALLOWED_MICS = {"XNAS", "XNYS", "XASE", "ARCX", "BATS"}   # NASDAQ/NYSE/AMEX family
_PROFILE_TTL_S = 7 * 24 * 3600
_FIN_TTL_S = 3 * 24 * 3600
_INSIDER_TTL_S = 3 * 24 * 3600     # A4 P11 cache budget
_NEWS_TTL_S = 12 * 3600            # GATE 1: news is time-sensitive -> short TTL, but
                                   # cached within a day so coverage accumulates
_EARNINGS_TTL_S = 7 * 24 * 3600    # GATE 1: earnings dates move rarely
_SYMBOLS_TTL_S = 7 * 24 * 3600
_SYMBOLS_KEY = "sc:us_symbols"
_COVERAGE_KEY = "sc:coverage"      # GATE 1: last build's Stage-2 coverage report
_SHORTLIST_SIZE = 100              # GATE 1: Stage-2 (insider/catalyst/earnings) fan-out
# GATE 1: Stage-2 endpoints. Randomizing their per-run order (and logging it) means
# queue position never silently decides which signals exist for a name.
_STAGE2_ENDPOINTS = ("insider", "catalyst", "earnings", "filings")


# ---------------------------------------------------------------- pure helpers
def days_to_earnings(payload: Optional[dict[str, Any]]) -> Optional[int]:
    """Days to the NEXT upcoming earnings date from a Finnhub earnings-calendar
    payload. None => UNKNOWN (fetch failed OR no scheduled date) -- the B3 earnings
    guard fails closed on None. A successful-but-empty calendar also yields None,
    but fetch_status distinguishes the two (empty vs unavailable)."""
    if not payload:
        return None
    cal = payload.get("earningsCalendar") or payload.get("earnings") or []
    today = date.today()
    upcoming = []
    for e in cal:
        try:
            ed = date.fromisoformat(str(e.get("date"))[:10])
        except (ValueError, TypeError):
            continue
        if ed >= today:
            upcoming.append((ed - today).days)
    return min(upcoming) if upcoming else None


def _fetch_status(val: Any, empty: bool) -> str:
    """GATE 1/2 tri-state: 'unavailable' (fetch failed/None), 'empty' (searched, no
    data), or 'ok' (searched, has data). Persisted per symbol so blindness is
    distinguishable in the DB, never conflated with a zero."""
    if val is None:
        return "unavailable"
    return "empty" if empty else "ok"


def float_est_m(so_m: Optional[float]) -> Optional[float]:
    """SO-proxy inflates true float; F3/A3 1.1 documented 0.85 haircut, for TIER
    DISPLAY ONLY. The field is labeled 'SO-proxy (est)' -- never presented as true float."""
    return round(so_m * 0.85, 2) if so_m is not None else None


def float_tier(float_m: Optional[float]) -> Optional[str]:
    """A3 1.1 tiers (on the float_est haircut): runner <20 | low 20-50 | mid 50-150
    | standard 150-500 | large 500-1000M. None => >1B (in universe, but no lane
    matches -> never triggers). Float is NEVER a universe gate."""
    if float_m is None:
        return None
    if float_m < 20:
        return "runner"
    if float_m < 50:
        return "low"
    if float_m < 150:
        return "mid"
    if float_m <= 500:
        return "standard"
    if float_m <= FLOAT_CAP_M:
        return "large"
    return None


def price_tier(price: Optional[float]) -> Optional[str]:
    """A3 Part 2: deep $0.20-1 | sub2 $1-2 | low $2-5 | special $5-10."""
    if price is None:
        return None
    if price < 1.0:
        return "deep"
    if price < 2.0:
        return "sub2"
    if price < 5.0:
        return "low"
    if price <= 10.0:
        return "special"
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


def _base_weekly(df: pd.DataFrame) -> dict[str, Any]:
    """Base / breakout / retest (daily) + weekly-momentum signals. Feeds the
    BREAKOUT lane gate and the structure family (Addendum 6 weekly logic)."""
    out: dict[str, Any] = {}
    close, high, low, vol = df["Close"], df["High"], df["Low"], df["Volume"]
    c = float(close.iloc[-1])
    # daily base = the 15 bars BEFORE today; range < 30% of its low
    if len(df) >= 20:
        base = df.iloc[-16:-1]
        bh, bl = float(base["High"].max()), float(base["Low"].min())
        rng = (bh - bl) / bl if bl else 1.0
        out["daily_base"] = bool(rng < 0.30)
        out["base_high"] = round(bh, 4)
        out["broke_out"] = bool(c > bh and rng < 0.30)
        # retest: a close crossed base_high in the last 10d, now back at/above it, holding
        crossed = bool((close.iloc[-11:-1] > bh).any())
        out["retest"] = bool(crossed and bh <= c <= bh * 1.05 and float(low.iloc[-1]) >= bh * 0.97)
    # weekly momentum
    wk = df.resample("W-FRI").agg({"High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna()
    if len(wk) >= 9:
        wc, wv, wl = wk["Close"], wk["Volume"], wk["Low"]
        prior8_hi = float(wc.iloc[-9:-1].max())
        v8 = float(wv.iloc[-9:-1].mean())
        out["weekly_breakout"] = bool(wc.iloc[-1] > prior8_hi and v8 > 0 and wv.iloc[-1] > 1.5 * v8)
        b6 = wk.iloc[-6:]
        wrng = (float(b6["High"].max()) - float(b6["Low"].min())) / max(1e-9, float(b6["Low"].min()))
        out["weekly_base"] = bool(wrng < 0.30)
        lows = wl.iloc[-4:].tolist()
        out["weekly_higher_lows"] = bool(len(lows) >= 4 and lows[1] > lows[0] and lows[2] > lows[1] and lows[3] > lows[2])
    return out


def demand_trend_features(df: pd.DataFrame) -> dict[str, Any]:
    """OHLC inputs the lane rubrics need (SMA20/50/200 + slope, %off-60d-high,
    selling exhaustion, undercut-reclaim, recent-runner, prior-day close,
    support-level context, and base/breakout/retest + weekly momentum)."""
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
    feat.update(_base_weekly(df))
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
                  splits: Optional[pd.Series] = None, *,
                  stage2: bool = True,
                  endpoint_order: Optional[list[str]] = None) -> dict[str, Any]:
    """Screen + enrich one symbol. Returns {status, symbol, [row]}. status is one
    of: added | deathwatch | skip_price | skip_liquidity | skip_float | skip_data.

    GATE 1 two-stage: STAGE 1 (stage2=False) does the yfinance OHLC screen +
    profile + fundamentals (universe-wide, cheap-per-cache). STAGE 2 (stage2=True,
    shortlist only) additionally fetches insider / catalyst / earnings / filings in
    `endpoint_order` (randomized per run so queue position never decides coverage).
    A Stage-1 row carries the Stage-2 families as UNAVAILABLE with fetch_status
    'pending' -- never as a zero."""
    import yfinance as yf
    if df is None:
        tk = yf.Ticker(symbol)
        df = tk.history(period="2y", interval="1d", auto_adjust=True)   # sma200 + 18mo split lookback
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

    # ---- STAGE 1 (universe-wide): profile (float) + fundamentals ----
    prof = _cached(db, f"sc:profile2:{symbol}", _PROFILE_TTL_S, lambda: fh.profile2(symbol)) or {}
    so_m = prof.get("shareOutstanding")
    fl_est = float_est_m(so_m)              # SO-proxy 0.85 haircut, tier display only
    tier = float_tier(fl_est)
    ptier = price_tier(price)
    bf = _cached(db, f"sc:fin:{symbol}", _FIN_TTL_S, lambda: fh.basic_financials(symbol)) or {}
    metric = bf.get("metric", {}) or {}
    series = bf.get("series", {}) or {}
    r52 = edges.range52_beta(metric, price)

    # ---- STAGE 2 (shortlist only): insider / catalyst / earnings / filings ----
    # Defaults = UNAVAILABLE (None) so a Stage-1 row's thesis families are excluded,
    # never scored as zero. Fetched in `endpoint_order` so no endpoint is always last.
    news = txns = filings = earn = None
    if stage2:
        for ep in (endpoint_order or list(_STAGE2_ENDPOINTS)):
            if ep == "insider":
                txns = _cached(db, f"sc:insider:{symbol}", _INSIDER_TTL_S,
                               lambda: fh.insider_transactions(symbol))
            elif ep == "catalyst":
                news = _cached(db, f"sc:news:{symbol}", _NEWS_TTL_S,
                               lambda: fh.company_news(symbol, days=7))
            elif ep == "earnings":
                earn = _cached(db, f"sc:earn:{symbol}", _EARNINGS_TTL_S,
                               lambda: fh.earnings_for_symbol(symbol))
            elif ep == "filings":
                filings = _cached(db, f"sc:filings:{symbol}", _FIN_TTL_S,
                                  lambda: fh.filings(symbol, 180))

    now_ts = datetime.now(timezone.utc).timestamp()
    catalyst = catalyst_from_news(news, now_ts, 48)
    news_class = edges.classify_news(news, now_ts, window_days=7)   # None -> neutral/0
    insider_data = (txns or {}).get("data") if isinstance(txns, dict) else None
    insider = edges.insider_score(insider_data, market_cap_m=prof.get("marketCapitalization"))
    dilution_risk, dil_forms = dilution_from_filings(filings)
    dte = days_to_earnings(earn)

    # GATE 1/2: per-Stage-2-family fetch status, persisted so the DB distinguishes
    # unavailable (fetch failed) from empty (searched, nothing) -- never conflated.
    fetch_status = {
        "insider": _fetch_status(txns, empty=(insider_data == [])),
        "catalyst": _fetch_status(news, empty=(news == [])),
        "earnings": _fetch_status(earn, empty=(earn is not None and dte is None)),
        "filings": _fetch_status(filings, empty=(filings == [])),
    } if stage2 else {ep: "pending" for ep in _STAGE2_ENDPOINTS}

    signals_blob = {
        "ohlc": sig,
        "demand_trend": demand_trend_features(df),
        "fundamentals": value_fundamentals(metric, so_m),
        "catalyst": catalyst,
        "catalyst_class": {"weight": news_class["weight"], "type": news_class["type"]},
        # news_available = the feed was SEARCHED (None => unavailable, [] => empty/drag)
        "news_available": news is not None,
        "going_concern": news_class["going_concern"],
        "insider": insider,
        "fundamental_trends": {"revenue_trend": edges.revenue_trend(series)},
        "pct_of_52w_range": r52["pct_of_52w_range"],
        "pct_from_52w_high": r52["pct_from_52w_high"],
        "beta": r52["beta"],
        "reverse_split": ss.reverse_split_flags(splits),
        "dilution_forms": dil_forms,
        "days_to_earnings": dte,         # None => UNKNOWN (B3 earnings guard fails closed)
        "fetch_status": fetch_status,
        "stage2_enriched": bool(stage2),
    }
    delisting_risk = 1 if (sig.get("sub_dollar_streak") or 0) > 20 else 0
    signals_blob["delisting_risk"] = delisting_risk
    row = {
        "symbol": symbol,
        "price": price,
        "price_tier": ptier,
        "exchange": prof.get("exchange"),
        "sector_name": prof.get("finnhubIndustry"),
        "float_shares": so_m,
        "float_est": fl_est,
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
            "dilution_risk": dilution_risk, "catalyst": bool(catalyst),
            "stage2": bool(stage2), "row": {**row, "signals": signals_blob}}


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
            # actions=True brings a "Stock Splits" column in the SAME batch, so we
            # never make per-name yf.Ticker(sym).splits calls (which Yahoo
            # rate-limits/blocks right after a large batch -> whole build errors)
            data = yf.download(chunk, period="2y", interval="1d", auto_adjust=True,
                               group_by="ticker", threads=True, progress=False, actions=True)
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

    def _splits_of(sub: pd.DataFrame):
        try:
            if "Stock Splits" in sub:
                s = sub["Stock Splits"]
                return s[s != 0]
        except Exception:
            pass
        return None

    import random
    from src import smallcap_lanes as _L

    # ---- STAGE 1 (universe-wide): profile + fundamentals; thesis families left
    # UNAVAILABLE. Rank survivors by a permissive prescore to pick the shortlist. ----
    sub_map: dict[str, tuple] = {}
    ranked: list[tuple[str, float]] = []
    for sym, sub in survivors:
        splits = _splits_of(sub)
        sub_map[sym] = (sub, splits)
        try:
            r = enrich_symbol(db, fh, sym, df=sub, splits=splits, stage2=False)
            counts[r["status"]] = counts.get(r["status"], 0) + 1
            if r["status"] == "added":
                ranked.append((sym, _L.stage1_prescore(r["row"])))
        except Exception as exc:
            logger.debug("stage1 %s failed: %s", sym, exc)
            counts["error"] = counts.get("error", 0) + 1

    ranked.sort(key=lambda x: -x[1])
    shortlist = ranked[:_SHORTLIST_SIZE]
    cutoff = (shortlist[-1][1] if len(shortlist) >= _SHORTLIST_SIZE
              else (ranked[-1][1] if ranked else 0.0))
    logger.info("GATE1 shortlist cut: %d added -> top %d for Stage 2; cutoff composite "
                "(the %dth name)=%.2f  [a HIGH cutoff means the shortlist is too small and "
                "good candidates never get their insider/catalyst data]",
                len(ranked), len(shortlist), len(shortlist), cutoff)

    # ---- STAGE 2 (shortlist only): insider/catalyst/earnings/filings in a
    # RANDOMIZED, LOGGED endpoint order so queue position never decides coverage. ----
    fh.reset_call_stats()
    order = list(_STAGE2_ENDPOINTS)
    random.shuffle(order)
    logger.info("GATE1 Stage-2 endpoint order this run: %s", order)
    for sym, _score in shortlist:
        sub, splits = sub_map.get(sym, (None, None))
        try:
            enrich_symbol(db, fh, sym, df=sub, splits=splits, stage2=True, endpoint_order=order)
        except Exception as exc:
            logger.debug("stage2 %s failed: %s", sym, exc)
            counts["stage2_error"] = counts.get("stage2_error", 0) + 1

    # ---- coverage report: the permanent health surface + the lane-re-enable input ----
    report = coverage_report(db, [s for s, _ in shortlist], fh.call_stats,
                             endpoint_order=order, cutoff=cutoff)
    db.cache_put(_COVERAGE_KEY, report)
    counts["shortlist"] = len(shortlist)
    counts["shortlist_cutoff_composite"] = round(cutoff, 2)
    counts["coverage_pct"] = {ep: report["endpoints"][ep]["coverage_pct"]
                              for ep in report["endpoints"]}
    logger.info("smallcap build done: %s", counts)
    return counts


_EP_PATH = {"insider": "/stock/insider-transactions", "catalyst": "/company-news",
            "earnings": "/calendar/earnings", "filings": "/stock/filings"}


def coverage_report(db: Database, shortlist_syms: list[str], call_stats: dict,
                    *, endpoint_order: Optional[list[str]] = None,
                    cutoff: Optional[float] = None) -> dict[str, Any]:
    """GATE 1 health surface. Per Stage-2 endpoint over the shortlist:
    attempted / succeeded / empty / unavailable (from persisted fetch_status) plus
    this run's rate_limited / error call counts. DEGRADED when coverage < 80%."""
    rows = {r["symbol"]: r for r in db.get_smallcap_universe(max_age_hours=None)}
    n = len(shortlist_syms)
    endpoints: dict[str, Any] = {}
    for ep in _STAGE2_ENDPOINTS:
        ok = empty = unavail = 0
        for s in shortlist_syms:
            fs = ((rows.get(s) or {}).get("signals") or {}).get("fetch_status") or {}
            st = fs.get(ep, "pending")
            if st == "ok":
                ok += 1
            elif st == "empty":
                empty += 1
            else:
                unavail += 1
        got = ok + empty
        cov = round(100 * got / n, 1) if n else 0.0
        cs = call_stats.get(_EP_PATH[ep], {})
        endpoints[ep] = {"attempted": n, "succeeded": ok, "empty": empty,
                         "unavailable": unavail, "coverage_pct": cov,
                         "rate_limited": cs.get("rate_limited", 0), "error": cs.get("error", 0),
                         "degraded": cov < 80.0}
    return {"as_of": datetime.now(timezone.utc).isoformat(), "shortlist": n,
            "endpoint_order": endpoint_order or list(_STAGE2_ENDPOINTS),
            "shortlist_cutoff_composite": round(cutoff, 2) if cutoff is not None else None,
            "endpoints": endpoints}


def latest_coverage(db: Database) -> Optional[dict[str, Any]]:
    return (db.cache_get(_COVERAGE_KEY) or {}).get("payload")
