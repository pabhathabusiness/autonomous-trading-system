"""
Multi-edge, confidence-tiered technical analysis for a single symbol.

Instead of a single pass/fail quality cutoff, every setup is scored by a
STACK OF INDEPENDENT EDGES. Each edge either fires or it doesn't; the more
edges that align, the higher the confidence tier:

    HIGH   -> many edges align (or quality >= high_quality)
    MEDIUM -> several edges align
    LOW    -> a few edges align
    NONE   -> too few; not surfaced

Edges span multiple timeframes (4h / daily / weekly), classic indicators
(MACD, Bollinger, RSI, moving-average / golden cross), microstructure
(volume profile, RVOL), chart patterns, and a fundamental analyst-target
edge. `quality_score` (0-10) is the normalized weighted magnitude; the
tier is driven primarily by HOW MANY edges fire, which is what "confidence
by number of edges" means.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import pandas as pd
import yfinance as yf

from src import chart_patterns, indicators

logger = logging.getLogger(__name__)

TIER_RANK = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}


def _resample_4h(hourly: pd.DataFrame) -> pd.DataFrame:
    if hourly.empty:
        return hourly
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    cols = [c for c in agg if c in hourly.columns]
    return hourly[cols].resample("4h").agg({c: agg[c] for c in cols}).dropna()


# SPY closes power the relative-strength-vs-market edge. Fetched once and cached
# for an hour so a full-universe scan doesn't re-download the benchmark per name.
_SPY_CACHE: dict[str, Any] = {"ts": None, "closes": None}


def _benchmark_closes(ttl_seconds: int = 3600):
    import time
    now = time.time()
    if _SPY_CACHE["closes"] is not None and _SPY_CACHE["ts"] and now - _SPY_CACHE["ts"] < ttl_seconds:
        return _SPY_CACHE["closes"]
    try:
        df = yf.Ticker("SPY").history(period="1y", interval="1d", auto_adjust=True)
        closes = df["Close"].dropna() if df is not None and not df.empty else None
    except Exception:
        closes = None
    _SPY_CACHE["closes"] = closes
    _SPY_CACHE["ts"] = now
    return closes


# Every scoring engine files its sub-signals under these five dimensions and
# caps each so no single family (esp. momentum) can dominate. quality_score is
# the direct 0-10 sum of the capped dimension scores. One implementation, used
# by all four engines, so the capping rule is identical everywhere.
_DIM_CAP = 2.0
_DIMENSIONS = ("structure", "momentum", "volatility", "volume", "rel_strength")


def _new_dims() -> dict[str, list[dict[str, Any]]]:
    return {d: [] for d in _DIMENSIONS}


def _aggregate_dims(dims: dict[str, list[dict[str, Any]]],
                    caps: Optional[dict[str, float]] = None):
    """(dim_scores, quality, fired_names, num_edges) from the capped dims."""
    caps = caps or {}
    dim_scores = {d: round(min(caps.get(d, _DIM_CAP), sum(s["points"] for s in subs)), 2)
                  for d, subs in dims.items()}
    quality = round(sum(dim_scores.values()), 2)
    fired = [s["name"] for subs in dims.values() for s in subs if s["fired"]]
    return dim_scores, quality, fired, len(fired)


class TechnicalAnalyzer:
    def __init__(self, config: dict[str, Any]):
        tcfg = config.get("technical", {})
        self.pivot_order = tcfg.get("pivot_lookback", 3)
        self.bb_period = tcfg.get("bollinger_period", 20)
        self.bb_std = tcfg.get("bollinger_std", 2.0)
        self.macd_fast = tcfg.get("macd_fast", 12)
        self.macd_slow = tcfg.get("macd_slow", 26)
        self.macd_signal = tcfg.get("macd_signal", 9)
        self.min_stop_pct = tcfg.get("min_stop_pct", 0.04)
        self.max_target_mult = tcfg.get("max_target_mult", 1.6)
        # ignore resistance pivots sitting right on top of price (a target a
        # few pennies away yields nonsense R:R); require a meaningful move.
        self.min_reward_pct = tcfg.get("min_reward_pct", 0.05)
        self.default_target_pct = tcfg.get("default_target_pct", 0.15)
        # "weekly" -> take resistance/targets from higher-timeframe swing highs
        # (bigger, fewer, further away); "daily" -> use daily pivots.
        self.resistance_source = tcfg.get("target_resistance_source", "weekly")
        self.buying_lookback = tcfg.get("buying_pressure_lookback", 10)  # ~2 weeks
        st = tcfg.get("short_term", {})
        self.st_min_stop = st.get("min_stop_pct", 0.025)
        self.st_target_pct = st.get("target_pct", 0.06)
        self.st_breakout_lb = st.get("breakout_lookback", 10)
        tiers = tcfg.get("confidence_tiers", {})
        self.high_edges = tiers.get("high_min_edges", 9)
        self.medium_edges = tiers.get("medium_min_edges", 6)
        self.low_edges = tiers.get("low_min_edges", 4)
        self.high_quality = tiers.get("high_min_quality", 7.5)
        self.medium_quality = tiers.get("medium_min_quality", 5.5)
        self.low_quality = tiers.get("low_min_quality", 4.0)

    # ------------------------------------------------------------- data fetch
    @staticmethod
    def _history(symbol: str, period: str, interval: str) -> pd.DataFrame:
        try:
            df = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=True)
            return df.dropna() if df is not None else pd.DataFrame()
        except Exception as exc:
            logger.debug("history %s %s/%s failed: %s", symbol, period, interval, exc)
            return pd.DataFrame()

    @staticmethod
    def _analyst_target(symbol: str) -> Optional[float]:
        try:
            info = yf.Ticker(symbol).info
            return info.get("targetMeanPrice") or info.get("targetMedianPrice")
        except Exception:
            return None

    # ------------------------------------------------------------------ core
    def analyze(self, symbol: str, fundamentals: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
        daily = self._history(symbol, "1y", "1d")
        weekly = self._history(symbol, "2y", "1wk")
        hourly = self._history(symbol, "60d", "1h")
        four_h = _resample_4h(hourly)

        if daily.empty or len(daily) < self.bb_period + 5:
            return None

        closes = daily["Close"]
        price = float(closes.iloc[-1])

        # ---- capped-dimension scoring -----------------------------------
        # Every sub-signal is filed under ONE of five dimensions. Each
        # dimension is capped (default 2.0) so no single family -- momentum
        # especially -- can dominate the score. quality_score is the direct
        # sum of the (capped) dimension scores, 0-10. R:R and the analyst
        # target are computed but deliberately kept OUT of the score (R:R is a
        # gate + grade input; the analyst target is logged context only).
        dims = _new_dims()

        def sig(dim: str, name: str, fired: bool, points: float, detail: str = "") -> None:
            dims[dim].append({"name": name, "fired": bool(fired),
                              "points": float(points) if fired else 0.0,
                              "detail": detail})

        # --- STRUCTURE ---------------------------------------------------
        d_highs, d_lows = indicators.find_pivots(daily, self.pivot_order)
        w_highs, w_lows = indicators.find_pivots(weekly, 2) if len(weekly) > 10 else ([], [])
        daily_bias = indicators.structure_bias(d_highs, d_lows)
        weekly_bias = indicators.structure_bias(w_highs, w_lows)
        bull_tf = (daily_bias == "BULLISH") + (weekly_bias == "BULLISH")
        sig("structure", "mtf_structure", bull_tf >= 1, 2.0 if bull_tf == 2 else 1.0,
            f"daily {daily_bias}/weekly {weekly_bias}")

        # --- MOMENTUM: EMAs (9/21 timing, 20/50 swing, 50/200 backdrop) --
        # The 50/200 EMA read IS the golden/death cross -- it lives here as one
        # capped momentum sub-signal, NOT double-counted as a separate edge.
        ema_9_21 = indicators.ema_alignment(closes, 9, 21, "up")
        ema_20_50 = indicators.ema_alignment(closes, 20, 50, "up")
        ema_50_200 = indicators.ema_alignment(closes, 50, 200, "up")
        sig("momentum", "ema_9_21", bool(ema_9_21), 0.6, "EMA9 > EMA21 (intraday timing up)")
        sig("momentum", "ema_20_50", bool(ema_20_50), 0.8, "EMA20 > EMA50 (swing trend up)")
        sig("momentum", "ema_50_200", bool(ema_50_200), 0.6, "EMA50 > EMA200 (golden-cross backdrop)")

        # --- MOMENTUM: MACD across timeframes ----------------------------
        macd_d = indicators.macd(closes, self.macd_fast, self.macd_slow, self.macd_signal)
        sig("momentum", "macd_daily", macd_d["signal"] in ("BULLISH", "BULLISH_CROSSOVER"),
            0.8 if macd_d["signal"] == "BULLISH_CROSSOVER" else 0.6, f"daily MACD {macd_d['signal']}")
        macd_w = indicators.macd(weekly["Close"]) if len(weekly) > 30 else {"signal": "NEUTRAL"}
        macd_4h = indicators.macd(four_h["Close"]) if len(four_h) > 30 else {"signal": "NEUTRAL"}
        bullish_macd_tf = sum(
            m["signal"] in ("BULLISH", "BULLISH_CROSSOVER") for m in (macd_d, macd_w, macd_4h)
        )
        sig("momentum", "macd_mtf_confluence", bullish_macd_tf >= 2, 0.6,
            f"{bullish_macd_tf}/3 timeframes bullish (4h/D/W)")

        # --- MOMENTUM: ROC + MFI (volume-weighted; replaces RSI) ---------
        roc10 = indicators.roc(closes, 10) or 0.0
        sig("momentum", "momentum_roc", roc10 > 0, 0.5, f"10-bar ROC {roc10:+.1f}%")
        mfi_d = indicators.mfi(daily)
        mfi_edge = (50 <= mfi_d <= 80) or (mfi_d < 20)
        sig("momentum", "mfi_regime", mfi_edge, 0.6,
            f"MFI {mfi_d:.0f} ({'money flowing in' if mfi_d >= 50 else 'washed-out'})")

        # --- VOLATILITY / COMPRESSION ------------------------------------
        bb = indicators.bollinger_bands(closes, self.bb_period, self.bb_std)
        sig("volatility", "squeeze", bool(bb["squeeze"]), 1.0, "Bollinger squeeze (coiling)")
        sig("volatility", "bb_position", bb["position"] == "NEAR_LOWER", 0.6,
            "price near lower band (reversion long)")
        # compression is a TIMING signal -- direction comes from which pivot it
        # resolves against. A squeeze resolving UP through the upper band = a
        # long-side timing trigger.
        compression_up = bool(bb["squeeze"] and bb["breakout"])
        sig("volatility", "compression_resolve_up", compression_up, 0.6,
            "squeeze resolving up through band")

        # --- VOLUME ------------------------------------------------------
        avg_vol = daily["Volume"].rolling(20).mean().iloc[-1]
        last_vol = float(daily["Volume"].iloc[-1])
        vol_confirmed = bool(pd.notna(avg_vol) and last_vol > avg_vol)
        sig("volume", "volume_confirmation", vol_confirmed, 0.5, "volume > 20-bar avg")

        rvol = None
        if fundamentals and fundamentals.get("rvol") is not None:
            rvol = fundamentals["rvol"]
        elif pd.notna(avg_vol) and avg_vol > 0:
            rvol = last_vol / float(avg_vol)
        sig("volume", "relative_volume", bool(rvol and rvol > 1.0),
            0.8 if (rvol or 0) > 1.5 else 0.6, f"RVOL {rvol:.2f}" if rvol else "RVOL n/a")

        recent = daily.tail(self.buying_lookback + 1)
        delta = recent["Close"].diff().dropna()
        vols = recent["Volume"].iloc[1:]
        up_vol = float(vols[delta > 0].sum())
        down_vol = float(vols[delta < 0].sum())
        buy_ratio = (up_vol / down_vol) if down_vol > 0 else (2.0 if up_vol > 0 else 0.0)
        sig("volume", "buying_pressure", buy_ratio > 1.1, 0.6,
            f"{self.buying_lookback}d up/down vol {buy_ratio:.2f}")

        vp = indicators.volume_profile(daily.tail(120))
        vp_support = False
        vp_detail = "no profile"
        if vp["poc"]:
            near_hvn = any(abs(price - h) / price <= 0.04 and price >= h * 0.98 for h in vp["hvns"])
            above_poc = price >= vp["poc"]
            vp_support = bool(above_poc or near_hvn)
            vp_detail = f"POC {vp['poc']}, {'above POC' if above_poc else 'at HVN support'}"
        sig("volume", "volume_profile", vp_support, 0.6, vp_detail)

        # --- REL_STRENGTH vs SPY -----------------------------------------
        bench = _benchmark_closes()
        rs20 = indicators.relative_strength(closes, bench, 20) if bench is not None else None
        rs60 = indicators.relative_strength(closes, bench, 60) if bench is not None else None
        sig("rel_strength", "rs_vs_spy_20", bool(rs20 is not None and rs20 > 0),
            1.4 if (rs20 or 0) > 5 else 1.0, f"20d RS vs SPY {rs20:+.1f}%" if rs20 is not None else "RS n/a")
        sig("rel_strength", "rs_vs_spy_60", bool(rs60 is not None and rs60 > 0), 0.8,
            f"60d RS vs SPY {rs60:+.1f}%" if rs60 is not None else "RS n/a")

        # --- STRUCTURE: chart patterns (daily AND weekly) ----------------
        patterns_d = chart_patterns.detect_all(daily.tail(60))
        patterns_w = chart_patterns.detect_all(weekly.tail(40)) if len(weekly) > 20 else {}
        patterns = {f"{k} (D)": v for k, v in patterns_d.items()}
        patterns.update({f"{k} (W)": v for k, v in patterns_w.items()})
        pattern_points = 1.2 if patterns_w else (1.0 if patterns_d else 0.0)
        sig("structure", "chart_pattern", len(patterns) > 0, pattern_points,
            "; ".join(patterns.values()) if patterns else "none")

        # --- risk / reward + entry location ------------------------------
        support = indicators.nearest_level(d_lows, price, "below")
        # Resistance/target from WEEKLY swing highs: higher-timeframe supply
        # zones are fewer, more significant, and sit further away -- giving the
        # trade room instead of tripping over every minor daily pivot. Fall
        # back to daily highs only if the weekly gives nothing overhead.
        res_pool = w_highs if (self.resistance_source == "weekly" and w_highs) else d_highs
        resistance = indicators.nearest_level(res_pool, price, "above")

        # Stop below the nearest demand zone, but never tighter than a floor
        # (otherwise a swing stop 1% away produces absurd R:R on penny names).
        support_stop = support * 0.97 if support else price * (1 - 0.08)
        floor_stop = price * (1 - self.min_stop_pct)
        stop_loss = round(min(support_stop, floor_stop), 4)

        # The 12-month analyst target informs the `analyst_target` EDGE, but is
        # NOT used as the swing objective -- that would give unrealistic R:R.
        # The trade objective is the nearest supply zone, capped to a sane move.
        analyst_target = None
        if fundamentals and fundamentals.get("price_target"):
            analyst_target = fundamentals["price_target"]
        else:
            analyst_target = self._analyst_target(symbol)

        ceiling = price * self.max_target_mult
        # target the nearest supply zone that is a MEANINGFUL distance above
        # price -- pivots within min_reward_pct are noise, not objectives.
        def _meaningful(pool: list) -> Optional[float]:
            return indicators.nearest_level(
                [(t, h) for (t, h) in pool if h >= price * (1 + self.min_reward_pct)],
                price, "above")
        meaningful_res = _meaningful(res_pool)
        if not meaningful_res and self.resistance_source == "weekly":
            meaningful_res = _meaningful(d_highs)  # fall back to daily
        if meaningful_res and meaningful_res > price:
            target = min(meaningful_res, ceiling)
        else:
            target = min(price * (1 + self.default_target_pct), ceiling)
        target = round(float(target), 4)
        if target <= price * (1 + self.min_reward_pct):
            target = round(price * (1 + self.default_target_pct), 4)

        risk = price - stop_loss
        reward = target - price
        risk_reward = round(reward / risk, 2) if risk > 0 else 0.0
        # R:R is a GATE + grade input -- NOT scored into quality.

        # entry location is a structure read (are we buying at a demand zone,
        # not chasing into open air) -> filed under structure, capped there.
        near_demand = bool(support and (price - support) / price <= 0.06)
        sig("structure", "demand_zone_entry", near_demand, 1.0,
            f"entry near demand {support}" if support else "no demand zone")

        # Analyst target: LOGGED CONTEXT ONLY -- pulled out of the score.
        upside = ((analyst_target - price) / price * 100) if analyst_target else 0.0

        # --- aggregate capped dimensions ---------------------------------
        # each dimension is summed then capped so no family dominates; the
        # score is the direct 0-10 sum of the five capped dimension scores.
        dim_scores, quality, fired_names, num_edges = _aggregate_dims(dims)
        confidence = self._tier(num_edges, quality)

        compression_tf = "daily" if bb["squeeze"] else None
        compression_dir = "up" if compression_up else None
        archetype = self._classify_archetype(daily_bias, weekly_bias, near_demand,
                                              bb, patterns, compression_dir, "long")

        expected_return_pct = round((target - price) / price * 100, 2)

        return {
            "symbol": symbol,
            "quality_score": quality,
            "confidence": confidence,
            "num_edges": num_edges,
            "edges_fired": ", ".join(fired_names),
            "dimensions": {d: [s for s in subs] for d, subs in dims.items()},
            "dim_scores": dim_scores,
            "archetype": archetype,
            "timeframe_band": "1-2 week swing",
            "structure_bias": daily_bias,
            "daily_bias": daily_bias,
            "weekly_bias": weekly_bias,
            "monthly_bias": weekly_bias,  # weekly stands in for the higher TF label
            "confluence_score": round(bull_tf / 2, 2),
            "macd_signal": macd_d["signal"],
            "bb_position": bb["position"],
            "rsi": round(mfi_d, 2),          # schema-compat key; now carries MFI
            "mfi": round(mfi_d, 2),
            "rs_vs_spy": rs20,
            "compression_tf": compression_tf,
            "compression_dir": compression_dir,
            "nearest_support": support,
            "nearest_resistance": resistance,
            "current_price": price,
            "entry_price": price,
            "stop_loss": stop_loss,
            "target_price": target,
            "risk_reward": risk_reward,
            "expected_return_pct": expected_return_pct,
            "volume_confirmed": vol_confirmed,
            "rvol": round(rvol, 2) if rvol else None,
            "patterns": list(patterns.keys()),
            "analyst_target": analyst_target,
            "analyst_upside_pct": round(upside, 1) if analyst_target else None,
            "volume_profile": vp,
            "details": {
                "dimensions": dims,
                "dim_scores": dim_scores,
                "bb_percent_b": bb["percent_b"],
                "macd_histogram": macd_d["histogram"],
                "roc10": roc10,
                "mfi": round(mfi_d, 2),
                "rs_vs_spy_20": rs20,
                "rs_vs_spy_60": rs60,
            },
        }

    @staticmethod
    def _classify_archetype(daily_bias: str, weekly_bias: str, near_pivot: bool,
                            bb: dict[str, Any], patterns: Any,
                            compression_dir: Optional[str] = None,
                            direction: str = "long") -> str:
        """Coarse archetype label for grading + the trade journal. The same
        three keys describe both directions (the grader keys off them):

        LONG:
        - breakout_continuation: squeeze resolving up / band breakout /
          continuation pattern (pennant / box / ascending triangle).
        - reversal: a downtrend turning up off a demand zone / reversal pattern
          (falling wedge, double bottom, inverse H&S).
        - trending_pullback_to_pivot: the default -- an uptrend pulling back
          into a pivot/demand zone.

        SHORT (mirror):
        - breakout_continuation: squeeze resolving DOWN / breakdown pattern
          (H&S, descending triangle, bear flag, rising wedge, double top).
        - reversal: an uptrend topping into a supply zone.
        - trending_pullback_to_pivot: shorting a pullback to supply in a
          downtrend.
        """
        pat_blob = (" ".join(patterns.values()) if isinstance(patterns, dict)
                    else " ".join(patterns)).lower()
        if direction == "short":
            breakdown_pats = ("head and shoulders", "descending triangle", "bear flag",
                              "rising wedge", "double top", "bearish")
            if compression_dir == "down" or any(p in pat_blob for p in breakdown_pats):
                return "breakout_continuation"
            uptrend = "BULLISH" in (daily_bias, weekly_bias)
            if uptrend and near_pivot:
                return "reversal"
            return "trending_pullback_to_pivot"
        breakout_pats = ("pennant", "flag", "box", "ascending triangle",
                         "cup", "rectangle")
        reversal_pats = ("falling wedge", "double bottom", "inverse head",
                         "inverse h&s", "bullish divergence")
        if compression_dir == "up" or bb.get("breakout") or any(p in pat_blob for p in breakout_pats):
            return "breakout_continuation"
        downtrend = "BEARISH" in (daily_bias, weekly_bias)
        if downtrend and (near_pivot or any(p in pat_blob for p in reversal_pats)):
            return "reversal"
        return "trending_pullback_to_pivot"

    def analyze_short_term(self, symbol: str) -> Optional[dict[str, Any]]:
        """Fast momentum setup for a 5-10% pop in 1-3 days (ideally 1-2).

        Edge recipe (user-specified): Bollinger squeeze/compression, 4-hour
        MACD cross, break of a short-term downtrend (falling lower-highs),
        reclaim of a weekly pivot level, and an inside-day + 4h-MACD-cross
        confluence. Deliberately lenient -- it surfaces the best momentum
        names even at LOW confidence rather than returning nothing.
        """
        daily = self._history(symbol, "6mo", "1d")
        weekly = self._history(symbol, "2y", "1wk")
        hourly = self._history(symbol, "60d", "1h")
        four_h = _resample_4h(hourly)
        if daily.empty or len(daily) < 30:
            return None

        closes = daily["Close"]
        highs, lows = daily["High"], daily["Low"]
        price = float(closes.iloc[-1])
        dims = _new_dims()

        def sig(dim: str, name: str, fired: bool, points: float, detail: str = "") -> None:
            dims[dim].append({"name": name, "fired": bool(fired),
                              "points": float(points) if fired else 0.0, "detail": detail})

        macd_4h = indicators.macd(four_h["Close"]) if len(four_h) > 30 else {"signal": "NEUTRAL", "histogram": 0.0}
        macd_4h_bull = macd_4h["signal"] in ("BULLISH", "BULLISH_CROSSOVER")

        # --- VOLATILITY / COMPRESSION (the timing energy) ----------------
        bb_d = indicators.bollinger_bands(closes, self.bb_period, self.bb_std)
        bb4 = indicators.bollinger_bands(four_h["Close"]) if len(four_h) > 25 else {"position": "MIDDLE", "squeeze": False, "breakout": False}
        squeeze = bool(bb_d["squeeze"] or bb4.get("squeeze"))
        sig("volatility", "bb_squeeze", squeeze, 1.2, "Bollinger compression")
        compression_up = bool(squeeze and (bb_d.get("breakout") or bb4.get("breakout")))
        sig("volatility", "compression_resolve_up", compression_up, 0.8, "squeeze resolving up")

        # --- MOMENTUM: 4h MACD (cross weighted highest) + EMAs + MFI -----
        sig("momentum", "macd_4h", macd_4h_bull,
            1.0 if macd_4h["signal"] == "BULLISH_CROSSOVER" else 0.7, f"4h MACD {macd_4h['signal']}")
        sig("momentum", "ema_9_21", bool(indicators.ema_alignment(closes, 9, 21, "up")), 0.5,
            "EMA9 > EMA21 (intraday timing up)")
        sig("momentum", "ema_20_50", bool(indicators.ema_alignment(closes, 20, 50, "up")), 0.5,
            "EMA20 > EMA50 (trend up)")
        mfi_d = indicators.mfi(daily)
        sig("momentum", "mfi_room", 40 <= mfi_d <= 80, 0.6, f"MFI {mfi_d:.0f}")

        # --- STRUCTURE: downtrend break + weekly pivot + inside day ------
        ph, pl = indicators.find_pivots(daily.tail(30), 2)
        downtrend_break = False
        dt_detail = "no downtrend break"
        if len(ph) >= 2:
            lower_highs = ph[-1][1] < ph[-2][1]
            if lower_highs and price > ph[-1][1]:
                downtrend_break = True
                dt_detail = f"broke lower-high {ph[-1][1]:.2f}"
        sig("structure", "downtrend_break", downtrend_break, 1.0, dt_detail)

        w_highs, w_lows = indicators.find_pivots(weekly, 2) if len(weekly) > 10 else ([], [])
        weekly_levels = [lvl for _, lvl in (w_lows[-3:] + w_highs[-3:])]
        near_weekly = any(0 <= (price - lvl) / price <= 0.05 for lvl in weekly_levels)
        sig("structure", "weekly_pivot", near_weekly, 0.8,
            "holding weekly pivot" if near_weekly else "no weekly pivot nearby")

        inside_day = bool(highs.iloc[-1] <= highs.iloc[-2] and lows.iloc[-1] >= lows.iloc[-2])
        inside_conf = inside_day and macd_4h_bull
        sig("structure", "inside_day_macd", inside_conf, 0.6,
            "inside day + 4h MACD" if inside_conf else ("inside day" if inside_day else "no inside day"))

        # --- VOLUME (participation) --------------------------------------
        avg_vol = daily["Volume"].rolling(20).mean().iloc[-1]
        last_vol = float(daily["Volume"].iloc[-1])
        rvol = (last_vol / float(avg_vol)) if pd.notna(avg_vol) and avg_vol > 0 else None
        sig("volume", "volume_surge", bool(rvol and rvol > 1.0),
            1.0 if (rvol or 0) > 1.5 else 0.6, f"RVOL {rvol:.2f}" if rvol else "RVOL n/a")

        # --- REL_STRENGTH vs SPY -----------------------------------------
        bench = _benchmark_closes()
        rs20 = indicators.relative_strength(closes, bench, 20) if bench is not None else None
        rs60 = indicators.relative_strength(closes, bench, 60) if bench is not None else None
        sig("rel_strength", "rs_vs_spy_20", bool(rs20 is not None and rs20 > 0),
            1.4 if (rs20 or 0) > 5 else 1.0, f"20d RS vs SPY {rs20:+.1f}%" if rs20 is not None else "RS n/a")
        sig("rel_strength", "rs_vs_spy_60", bool(rs60 is not None and rs60 > 0), 0.8,
            f"60d RS vs SPY {rs60:+.1f}%" if rs60 is not None else "RS n/a")

        # --- stop / target: quick 5-10% move, risk capped 2.5-5% ----------
        support = indicators.nearest_level(pl, price, "below")
        raw_stop = support * 0.99 if support else price * 0.97
        stop_loss = round(min(max(raw_stop, price * 0.95), price * 0.975), 4)  # risk in [2.5%, 5%]
        resistance = indicators.nearest_level(ph, price, "above")
        if resistance and price * 1.05 <= resistance <= price * 1.12:
            target = round(resistance, 4)          # real level in the 5-10% zone
        else:
            target = round(price * 1.07, 4)        # default ~7% pop
        risk = price - stop_loss
        reward = target - price
        risk_reward = round(reward / risk, 2) if risk > 0 else 0.0

        dim_scores, quality, fired, num_edges = _aggregate_dims(dims)
        daily_bias = indicators.structure_bias(*indicators.find_pivots(daily, self.pivot_order))
        weekly_struct = indicators.structure_bias(w_highs, w_lows)
        near_pivot = bool(near_weekly or (support and (price - support) / price <= 0.05))
        compression_tf = "daily/4h" if squeeze else None
        compression_dir = "up" if compression_up else None
        archetype = self._classify_archetype(daily_bias, weekly_struct, near_pivot,
                                              bb_d, [], compression_dir, "long")

        # short-term tier scaled to its stack (never NONE once surfaced)
        st_confidence = "HIGH" if num_edges >= 6 else "MEDIUM" if num_edges >= 4 else "LOW"

        return {
            "symbol": symbol,
            "quality_score": quality,
            "confidence": st_confidence,
            "num_edges": num_edges,
            "edges_fired": ", ".join(fired),
            "dimensions": {d: list(subs) for d, subs in dims.items()},
            "dim_scores": dim_scores,
            "archetype": archetype,
            "timeframe_band": "1-2 day",
            "daily_bias": daily_bias,
            "weekly_bias": f"4h {macd_4h['signal']}",
            "macd_signal": macd_4h["signal"],
            "bb_position": bb4.get("position", "MIDDLE"),
            "rsi": round(mfi_d, 2),          # schema-compat key; now carries MFI
            "mfi": round(mfi_d, 2),
            "rs_vs_spy": rs20,
            "compression_tf": compression_tf,
            "compression_dir": compression_dir,
            "nearest_support": support,
            "nearest_resistance": resistance,
            "current_price": price,
            "entry_price": price,
            "stop_loss": stop_loss,
            "target_price": target,
            "risk_reward": risk_reward,
            "expected_return_pct": round((target - price) / price * 100, 2),
            "rvol": round(rvol, 2) if rvol else None,
            "patterns": [],
            "analyst_target": None,
            "expected_timeframe": "1-2 days",
        }

    def analyze_coiling(self, symbol: str) -> Optional[dict[str, Any]]:
        """Detect a name COILING before a potential breakout -- the technical
        fingerprint of quiet accumulation ahead of a catalyst (the 'PLTR before
        it ran' look): a Bollinger squeeze while price is still flat, buyers
        stepping in (up-volume > down-volume), volume building, RSI with room,
        base intact. Not a buy-now -- a 'watch for the breakout' setup.
        """
        daily = self._history(symbol, "1y", "1d")
        if daily.empty or len(daily) < 60:
            return None
        closes = daily["Close"]
        price = float(closes.iloc[-1])
        edges: list[dict[str, Any]] = []

        def add(name: str, fired: bool, pts: float, mx: float, detail: str = "") -> None:
            edges.append({"name": name, "fired": bool(fired), "points": pts if fired else 0.0,
                          "max_points": mx, "detail": detail})

        # --- MULTI-TIMEFRAME Bollinger compression -----------------------
        # A monthly / quarterly squeeze is a multi-YEAR base coiling -- when it
        # breaks the move runs for months (the MU / SNDK pattern). Weighted
        # far heavier than a daily coil.
        bb = indicators.bollinger_bands(closes, self.bb_period, self.bb_std)
        weekly = self._history(symbol, "3y", "1wk")
        monthly = self._history(symbol, "max", "1mo")
        quarterly = monthly.resample("QE").agg(
            {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
        ).dropna() if not monthly.empty else monthly

        def squeeze_on(df, period, min_bars):
            if df is None or len(df) < min_bars:
                return None  # not enough history to judge
            return bool(indicators.bollinger_bands(df["Close"], period, self.bb_std)["squeeze"])

        sq_daily = bool(bb["squeeze"])
        sq_weekly = squeeze_on(weekly, self.bb_period, 40)
        sq_monthly = squeeze_on(monthly, 10, 24)      # ~2yr+ of monthly bars
        sq_quarterly = squeeze_on(quarterly, 8, 14)   # ~3.5yr+ of quarterly bars

        add("monthly_squeeze", bool(sq_monthly), 3.0, 3.0, "monthly Bollinger compression")
        add("quarterly_squeeze", bool(sq_quarterly), 2.5, 2.5, "quarterly compression (multi-yr base)")
        add("weekly_squeeze", bool(sq_weekly), 1.0, 1.0, "weekly compression")
        add("daily_squeeze", sq_daily, 0.5, 0.5, "daily compression")

        roc10 = indicators.roc(closes, 10) or 0.0
        add("flat_price", abs(roc10) < 6, 1.0, 1.0, f"price flat ({roc10:+.1f}% / 10d)")

        recent = daily.tail(11)
        delta = recent["Close"].diff().dropna()
        vols = recent["Volume"].iloc[1:]
        up_v, down_v = float(vols[delta > 0].sum()), float(vols[delta < 0].sum())
        buy_ratio = (up_v / down_v) if down_v > 0 else (2.0 if up_v > 0 else 0.0)
        add("accumulation", buy_ratio > 1.05, 1.5, 1.5, f"up/down vol {buy_ratio:.2f}")

        vol5 = float(daily["Volume"].tail(5).mean())
        vol20 = float(daily["Volume"].tail(20).mean())
        add("volume_building", vol20 > 0 and vol5 >= vol20, 1.0, 1.0,
            f"5d vol {'>' if vol5 >= vol20 else '<'} 20d avg")

        mfi_d = indicators.mfi(daily)
        add("mfi_room", 40 <= mfi_d <= 70, 1.0, 1.0, f"MFI {mfi_d:.0f}")

        sma50 = indicators.sma(closes, 50)
        add("base_intact", bool(sma50 and price >= sma50 * 0.97), 1.0, 1.0, "holding above 50MA")

        earned = sum(e["points"] for e in edges)
        possible = sum(e["max_points"] for e in edges)
        coil_score = round(10 * earned / possible, 2) if possible else 0.0
        num_edges = sum(1 for e in edges if e["fired"])
        fired = [e["name"] for e in edges if e["fired"]]

        # The strongest coils compress on the HIGHER timeframe. A genuine coil
        # = a monthly/quarterly squeeze (multi-year base) OR a weekly+daily
        # squeeze, with buyers stepping in while price is still flat.
        htf_squeeze = bool(sq_monthly or sq_quarterly)
        is_coiling = ((htf_squeeze or (bool(sq_weekly) and sq_daily))
                      and buy_ratio > 1.05 and abs(roc10) < 6)

        # label the biggest timeframe that's compressing + expected hold
        if sq_quarterly:
            comp_tf, hold = "QUARTERLY squeeze (multi-yr base)", "watch: multi-month breakout"
        elif sq_monthly:
            comp_tf, hold = "MONTHLY squeeze", "watch: multi-week/month breakout"
        elif sq_weekly:
            comp_tf, hold = "WEEKLY squeeze", "watch: breakout 2-6 wks"
        else:
            comp_tf, hold = "daily squeeze", "watch: breakout 1-3 wks"

        # breakout plan: bigger base -> bigger target
        upper = bb["upper"] or price * 1.03
        lower = bb["lower"] or price * 0.95
        trigger = round(max(upper, price), 4)
        stop_loss = round(min(lower, price * 0.92), 4)
        target_mult = 1.30 if sq_quarterly else 1.22 if sq_monthly else 1.15
        target = round(trigger * target_mult, 4)
        risk = trigger - stop_loss
        reward = target - trigger
        risk_reward = round(reward / risk, 2) if risk > 0 else 0.0

        # --- gradeable dimensions (parallel view; coil_score ranking above
        # is UNCHANGED -- compression is coiling's thesis). We surface the same
        # signals grouped into the five capped dimensions so the process grader
        # can measure breadth, plus archetype / band / RS for the journal.
        bench = _benchmark_closes()
        rs20 = indicators.relative_strength(closes, bench, 20) if bench is not None else None
        rs60 = indicators.relative_strength(closes, bench, 60) if bench is not None else None
        grade_dims = _new_dims()
        grade_dims["volatility"] = [
            {"name": "compression", "fired": bool(is_coiling), "points": 2.0 if is_coiling else 0.0,
             "detail": comp_tf}]
        grade_dims["volume"] = [
            {"name": "accumulation", "fired": buy_ratio > 1.05, "points": 1.2 if buy_ratio > 1.05 else 0.0,
             "detail": f"up/down vol {buy_ratio:.2f}"},
            {"name": "volume_building", "fired": vol20 > 0 and vol5 >= vol20,
             "points": 0.8 if (vol20 > 0 and vol5 >= vol20) else 0.0, "detail": "5d vs 20d vol"}]
        grade_dims["momentum"] = [
            {"name": "mfi_room", "fired": 40 <= mfi_d <= 70, "points": 0.8 if 40 <= mfi_d <= 70 else 0.0,
             "detail": f"MFI {mfi_d:.0f}"}]
        grade_dims["structure"] = [
            {"name": "base_intact", "fired": bool(sma50 and price >= sma50 * 0.97),
             "points": 1.0 if (sma50 and price >= sma50 * 0.97) else 0.0, "detail": "holding above 50MA"}]
        grade_dims["rel_strength"] = [
            {"name": "rs_vs_spy_20", "fired": bool(rs20 is not None and rs20 > 0),
             "points": (1.4 if (rs20 or 0) > 5 else 1.0) if (rs20 is not None and rs20 > 0) else 0.0,
             "detail": f"20d RS {rs20:+.1f}%" if rs20 is not None else "RS n/a"}]
        dim_scores, _q, _fired, _n = _aggregate_dims(grade_dims)

        return {
            "symbol": symbol,
            "coil_score": coil_score,
            "is_coiling": is_coiling,
            "compression_tf": comp_tf,
            "compression_dir": "up",      # a coil is a long-side (upside) breakout watch
            "confidence": self._tier(num_edges + 3, coil_score),  # coiling has fewer edges
            "quality_score": coil_score,  # UNCHANGED ranking key (compression thesis)
            "num_edges": num_edges,
            "edges_fired": ", ".join(fired),
            "dimensions": {d: list(subs) for d, subs in grade_dims.items()},
            "dim_scores": dim_scores,
            "archetype": "breakout_continuation",   # a coil is a pre-breakout base
            "timeframe_band": "1-2 week swing",
            "daily_bias": "COILING",
            "weekly_bias": comp_tf,
            "macd_signal": "n/a",
            "bb_position": comp_tf,
            "rsi": round(mfi_d, 2),         # schema-compat key; now carries MFI
            "mfi": round(mfi_d, 2),
            "rs_vs_spy": rs20,
            "current_price": price,
            "entry_price": trigger,       # buy on breakout above this
            "stop_loss": stop_loss,
            "target_price": target,
            "risk_reward": risk_reward,
            "expected_return_pct": round((target - trigger) / trigger * 100, 2),
            "rvol": None,
            "patterns": [],
            "analyst_target": None,
            "expected_timeframe": hold,
        }

    def analyze_downside(self, symbol: str, fundamentals: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
        """Bearish/short setup analysis -- the mirror image of `analyze`.

        Every long edge is inverted: lower-highs/lower-lows structure, price
        below falling MAs, death cross, MACD rolling over, rejection at the
        upper Bollinger band, distribution (down-volume > up-volume), breakdown
        below support, and analyst target BELOW price. Used for names in
        negative (downtrending) sectors. Returns direction='short'.
        """
        daily = self._history(symbol, "1y", "1d")
        weekly = self._history(symbol, "2y", "1wk")
        hourly = self._history(symbol, "60d", "1h")
        four_h = _resample_4h(hourly)
        if daily.empty or len(daily) < self.bb_period + 5:
            return None

        closes = daily["Close"]
        price = float(closes.iloc[-1])
        dims = _new_dims()

        def sig(dim: str, name: str, fired: bool, points: float, detail: str = "") -> None:
            dims[dim].append({"name": name, "fired": bool(fired),
                              "points": float(points) if fired else 0.0, "detail": detail})

        # --- STRUCTURE: lower-highs / lower-lows -------------------------
        d_highs, d_lows = indicators.find_pivots(daily, self.pivot_order)
        w_highs, w_lows = indicators.find_pivots(weekly, 2) if len(weekly) > 10 else ([], [])
        daily_bias = indicators.structure_bias(d_highs, d_lows)
        weekly_bias = indicators.structure_bias(w_highs, w_lows)
        bear_tf = (daily_bias == "BEARISH") + (weekly_bias == "BEARISH")
        sig("structure", "mtf_downtrend", bear_tf >= 1, 2.0 if bear_tf == 2 else 1.0,
            f"daily {daily_bias}/weekly {weekly_bias}")

        # --- MOMENTUM: EMAs down (50/200 = death cross) + MACD + MFI -----
        # 50/200 EMA IS the death cross -- one capped momentum sub-signal, not
        # double-counted as a separate edge.
        sig("momentum", "ema_9_21_down", bool(indicators.ema_alignment(closes, 9, 21, "down")), 0.6,
            "EMA9 < EMA21 (intraday timing down)")
        sig("momentum", "ema_20_50_down", bool(indicators.ema_alignment(closes, 20, 50, "down")), 0.8,
            "EMA20 < EMA50 (swing trend down)")
        sig("momentum", "ema_50_200_down", bool(indicators.ema_alignment(closes, 50, 200, "down")), 0.6,
            "EMA50 < EMA200 (death-cross backdrop)")
        macd_d = indicators.macd(closes, self.macd_fast, self.macd_slow, self.macd_signal)
        sig("momentum", "macd_daily_bear", macd_d["signal"] in ("BEARISH", "BEARISH_CROSSOVER"),
            0.8 if macd_d["signal"] == "BEARISH_CROSSOVER" else 0.6, f"daily MACD {macd_d['signal']}")
        macd_w = indicators.macd(weekly["Close"]) if len(weekly) > 30 else {"signal": "NEUTRAL"}
        macd_4h = indicators.macd(four_h["Close"]) if len(four_h) > 30 else {"signal": "NEUTRAL"}
        bear_macd = sum(m["signal"] in ("BEARISH", "BEARISH_CROSSOVER") for m in (macd_d, macd_w, macd_4h))
        sig("momentum", "macd_mtf_bear", bear_macd >= 2, 0.6, f"{bear_macd}/3 timeframes bearish")
        roc10 = indicators.roc(closes, 10) or 0.0
        sig("momentum", "momentum_down", roc10 < 0, 0.5, f"10-bar ROC {roc10:+.1f}%")
        mfi_d = indicators.mfi(daily)
        mfi_weak = (mfi_d <= 45) or (mfi_d > 80)
        sig("momentum", "mfi_weak", mfi_weak, 0.6,
            f"MFI {mfi_d:.0f} ({'overbought' if mfi_d > 80 else 'weak'})")

        # --- VOLATILITY: breakdown / rejection at upper band ------------
        bb = indicators.bollinger_bands(closes, self.bb_period, self.bb_std)
        below_lower = bool(bb["lower"] and price < bb["lower"])
        sig("volatility", "bollinger_breakdown", below_lower or bb["squeeze"], 1.0,
            "broke lower band" if below_lower else "squeeze")
        sig("volatility", "bollinger_rejection", bb["position"] == "NEAR_UPPER", 0.6, "rejected at upper band")
        compression_down = bool(bb["squeeze"] and below_lower)
        sig("volatility", "compression_resolve_down", compression_down, 0.6, "squeeze resolving down")

        # --- VOLUME: distribution (down-volume dominating) ---------------
        avg_vol = daily["Volume"].rolling(20).mean().iloc[-1]
        last_vol = float(daily["Volume"].iloc[-1])
        sig("volume", "volume_confirmation", bool(pd.notna(avg_vol) and last_vol > avg_vol), 0.5, "volume > avg")
        rvol = (last_vol / float(avg_vol)) if pd.notna(avg_vol) and avg_vol > 0 else None
        sig("volume", "relative_volume", bool(rvol and rvol > 1.0), 0.8 if (rvol or 0) > 1.5 else 0.6,
            f"RVOL {rvol:.2f}" if rvol else "RVOL n/a")
        recent = daily.tail(self.buying_lookback + 1)
        delta = recent["Close"].diff().dropna()
        vols = recent["Volume"].iloc[1:]
        up_v, down_v = float(vols[delta > 0].sum()), float(vols[delta < 0].sum())
        dist_ratio = (down_v / up_v) if up_v > 0 else (2.0 if down_v > 0 else 0.0)
        sig("volume", "distribution", dist_ratio > 1.1, 0.6, f"down/up vol {dist_ratio:.2f}")

        # --- REL_STRENGTH vs SPY (a short favours the laggards) ----------
        bench = _benchmark_closes()
        rs20 = indicators.relative_strength(closes, bench, 20) if bench is not None else None
        rs60 = indicators.relative_strength(closes, bench, 60) if bench is not None else None
        sig("rel_strength", "rs_vs_spy_20", bool(rs20 is not None and rs20 < 0),
            1.4 if (rs20 or 0) < -5 else 1.0, f"20d RS vs SPY {rs20:+.1f}%" if rs20 is not None else "RS n/a")
        sig("rel_strength", "rs_vs_spy_60", bool(rs60 is not None and rs60 < 0), 0.8,
            f"60d RS vs SPY {rs60:+.1f}%" if rs60 is not None else "RS n/a")

        # analyst target BELOW price -- LOGGED CONTEXT ONLY (kept out of score)
        analyst_target = (fundamentals or {}).get("price_target") or self._analyst_target(symbol)

        # --- risk / reward for a SHORT (gate + grade input, NOT scored) --
        # stop above (nearest resistance / weekly high), target below (support)
        res_pool = w_highs if (self.resistance_source == "weekly" and w_highs) else d_highs
        resistance = indicators.nearest_level(res_pool, price, "above")
        stop_above = resistance * 1.01 if resistance else price * 1.08
        stop_loss = round(min(max(stop_above, price * (1 + self.min_stop_pct)), price * 1.15), 4)

        sup_pool = w_lows if (self.resistance_source == "weekly" and w_lows) else d_lows
        support = indicators.nearest_level(sup_pool, price, "below")
        meaningful_sup = indicators.nearest_level(
            [(t, lv) for (t, lv) in sup_pool if lv <= price * (1 - self.min_reward_pct)], price, "below")
        if meaningful_sup and meaningful_sup < price:
            target = max(meaningful_sup, price * 0.70)
        else:
            target = price * (1 - self.default_target_pct)
        target = round(float(target), 4)

        risk = stop_loss - price
        reward = price - target
        risk_reward = round(reward / risk, 2) if risk > 0 else 0.0

        dim_scores, quality, fired, num_edges = _aggregate_dims(dims)
        # for a short, the pivot we lean on is the supply zone (resistance)
        near_supply = bool(resistance and (resistance - price) / price <= 0.06)
        compression_tf = "daily" if bb["squeeze"] else None
        compression_dir = "down" if compression_down else None
        archetype = self._classify_archetype(daily_bias, weekly_bias, near_supply,
                                              bb, [], compression_dir, "short")

        return {
            "symbol": symbol,
            "direction": "short",
            "quality_score": quality,
            "confidence": self._tier(num_edges, quality),
            "num_edges": num_edges,
            "edges_fired": ", ".join(fired),
            "dimensions": {d: list(subs) for d, subs in dims.items()},
            "dim_scores": dim_scores,
            "archetype": archetype,
            "timeframe_band": "1-2 week swing",
            "daily_bias": daily_bias,
            "weekly_bias": weekly_bias,
            "macd_signal": macd_d["signal"],
            "bb_position": bb["position"],
            "rsi": round(mfi_d, 2),          # schema-compat key; now carries MFI
            "mfi": round(mfi_d, 2),
            "rs_vs_spy": rs20,
            "compression_tf": compression_tf,
            "compression_dir": compression_dir,
            "nearest_support": support,
            "nearest_resistance": resistance,
            "current_price": price,
            "entry_price": price,
            "stop_loss": stop_loss,
            "target_price": target,
            "risk_reward": risk_reward,
            # gain if the short works (price falls to target)
            "expected_return_pct": round((price - target) / price * 100, 2),
            "rvol": round(rvol, 2) if rvol else None,
            "patterns": [],
            "analyst_target": analyst_target,
            "expected_timeframe": "1-3 weeks",
        }

    def _tier(self, num_edges: int, quality: float) -> str:
        if num_edges >= self.high_edges or quality >= self.high_quality:
            return "HIGH"
        if num_edges >= self.medium_edges or quality >= self.medium_quality:
            return "MEDIUM"
        if num_edges >= self.low_edges or quality >= self.low_quality:
            return "LOW"
        return "NONE"
