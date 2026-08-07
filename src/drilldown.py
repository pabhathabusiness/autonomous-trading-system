"""
Per-symbol timeframe-by-timeframe drill-down (the MAG-7 expand view).

Reads bias on 15m / 30m / 1h / 4h / daily (intraday from Alpaca, resampled for
30m/4h, daily from yfinance) and surfaces a trade plan ONLY when a genuine setup
exists. The gate is deliberately narrow:

  * COMPRESSION on 15m / 30m / 1h -- and only the unusual kind (see
    src/compression.py: bandwidth in the lowest decile of its own history, BB
    inside Keltner, and held for several bars). Ordinary narrow bands are not a
    setup and no longer arm anything.
  * A MACD CROSS on one of those same frames, which supplies the direction.
  * A PIVOT to trade against, so the stop sits at structure rather than at a
    round number.

4h is computed but never used to *enter*: it is too slow to time an entry off,
and its job here is to say how much fuel the move has. It is reported as a WATCH
-- armed with the exact upper/lower band levels to break, or already triggered.
The middle band (basis) on each frame supplies bias: price holding above a
rising basis is a different trade from price bleeding under a falling one, and a
plan that fights its own basis is flagged as conflicted rather than silently
taken.

No trade is manufactured for a name that doesn't have the confluence; bias is
always shown, a plan only when it's really there.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd
import yfinance as yf

from src import compression, indicators

_TFS = ["15m", "30m", "1h", "4h", "daily"]
# entry-timing frames: fast enough that a coil resolves inside a trade's life
_COMPRESSION_TFS = ("15m", "30m", "1h")
# context frame: computed, watched for a band break, never used to enter
_WATCH_TF = "4h"


def _resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    cols = [c for c in agg if c in df.columns]
    return df[cols].resample(rule).agg({c: agg[c] for c in cols}).dropna()


def _yf(symbol: str, period: str, interval: str) -> Optional[pd.DataFrame]:
    try:
        df = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=True)
        return df.dropna() if (df is not None and not df.empty) else None
    except Exception:
        return None


def _frames(alpaca, symbol: str) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    # prefer Alpaca's real-time IEX intraday bars when they come through...
    if alpaca and getattr(alpaca, "enabled", False):
        try:
            b15 = alpaca.bars([symbol], "15m", limit=400).get(symbol)
            b1h = alpaca.bars([symbol], "1h", limit=400).get(symbol)
        except Exception:
            b15 = b1h = None
        if b15 is not None and not b15.empty:
            frames["15m"] = b15
            frames["30m"] = _resample(b15, "30min")
        if b1h is not None and not b1h.empty:
            frames["1h"] = b1h
            frames["4h"] = _resample(b1h, "4h")
    # ...otherwise fall back to yfinance intraday (15m/60m), like the analyzer does
    if "15m" not in frames:
        y15 = _yf(symbol, "60d", "15m")
        if y15 is not None:
            frames["15m"] = y15
            frames.setdefault("30m", _resample(y15, "30min"))
    if "1h" not in frames:
        y1h = _yf(symbol, "6mo", "1h")
        if y1h is not None:
            frames["1h"] = y1h
            frames.setdefault("4h", _resample(y1h, "4h"))
    d = _yf(symbol, "1y", "1d")
    if d is not None:
        frames["daily"] = d
    return frames


def _tf_read(df: Optional[pd.DataFrame],
             settings: compression.Settings) -> Optional[dict[str, Any]]:
    if df is None or len(df) < 30:
        return None
    closes = df["Close"]
    price = float(closes.iloc[-1])
    ph, pl = indicators.find_pivots(df, 3)
    struct = indicators.structure_bias(ph, pl)
    ema_up = bool(indicators.ema_alignment(closes, 9, 21, "up"))
    ema_dn = bool(indicators.ema_alignment(closes, 9, 21, "down"))
    macd = indicators.macd(closes)
    sig = macd["signal"]
    # compression needs a long history to rank against and returns None without
    # it -- bias is still worth showing on a short frame, so this stays optional
    comp = compression.analyze(df, settings)
    bull = struct == "BULLISH" or (ema_up and "BULL" in sig)
    bear = struct == "BEARISH" or (ema_dn and "BEAR" in sig)
    bias = "Bullish" if (bull and not bear) else "Bearish" if (bear and not bull) else "Neutral"
    read = {
        "bias": bias,
        "macd": sig,
        "macd_cross": sig in ("BULLISH_CROSSOVER", "BEARISH_CROSSOVER"),
        "macd_dir": "up" if "BULL" in sig else "down" if "BEAR" in sig else "flat",
        # `squeeze` now means UNUSUAL compression, not merely narrow bands
        "squeeze": bool(comp and comp["unusual"]),
        "support": indicators.nearest_level(pl, price, "below"),
        "resistance": indicators.nearest_level(ph, price, "above"),
        "price": round(price, 2),
    }
    if comp:
        read.update({
            "compression": {
                "grade": comp["grade"], "unusual": comp["unusual"],
                "bandwidth_pctile": comp["bandwidth_pctile"],
                "bars_in_squeeze": comp["bars_in_squeeze"],
                "ttm_squeeze": comp["ttm_squeeze"], "label": comp["label"],
            },
            "bands": {"upper": comp["upper"], "middle": comp["middle"], "lower": comp["lower"]},
            "mid_bias": comp["mid"]["bias"],
            "mid_note": comp["mid"]["note"],
            "percent_b": comp["percent_b"],
        })
    return read


def _plan(reads: dict[str, dict[str, Any]],
          watch: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """A plan only when the confluence is genuinely there."""
    # 1) UNUSUAL compression on an entry-timing frame (15m/30m/1h)
    compressed = [tf for tf in _COMPRESSION_TFS if reads.get(tf) and reads[tf]["squeeze"]]
    if not compressed:
        return None
    # 2) a MACD cross on an entry-timing frame, with a direction
    trigger = next((tf for tf in _COMPRESSION_TFS
                    if reads.get(tf) and reads[tf]["macd_cross"]
                    and reads[tf]["macd_dir"] in ("up", "down")), None)
    if not trigger:
        return None
    r = reads[trigger]
    direction = "long" if r["macd_dir"] == "up" else "short"
    price = r["price"]
    # 3) a pivot to trade against
    if direction == "long":
        pivot = r["support"]
        if not pivot:
            return None
        entry, stop = price, round(pivot * 0.995, 2)
        target = round(r["resistance"] or price * 1.03, 2)
    else:
        pivot = r["resistance"]
        if not pivot:
            return None
        entry, stop = price, round(pivot * 1.005, 2)
        target = round(r["support"] or price * 0.97, 2)
    risk, reward = abs(entry - stop), abs(target - entry)
    rr = round(reward / risk, 2) if risk > 0 else 0.0

    # 4) basis + 4h context. Neither can create a trade; both can qualify one.
    wanted = "bullish" if direction == "long" else "bearish"
    mid_bias = r.get("mid_bias")
    mid_aligned = mid_bias == wanted
    mid_conflict = bool(mid_bias and mid_bias != "neutral" and mid_bias != wanted)
    htf_lean = (watch or {}).get("lean")
    htf_conflict = bool(htf_lean and htf_lean != direction)

    grade = (r.get("compression") or {}).get("grade", "unusual")
    bars = (r.get("compression") or {}).get("bars_in_squeeze")
    note = (f"{'; '.join(compressed)} {grade} compression"
            + (f" ({bars} bars)" if bars else "")
            + f" + {trigger} MACD {r['macd_dir']}-cross, {direction} against pivot {round(pivot, 2)}")
    if r.get("mid_note"):
        note += f"; basis {r['mid_note']}"

    caveats = []
    if mid_conflict:
        caveats.append(f"basis bias is {mid_bias} against a {direction}")
    if htf_conflict:
        caveats.append(f"4h leans {htf_lean}")

    return {
        "direction": direction, "trigger_tf": trigger, "compressed_tfs": compressed,
        "compression_grade": grade,
        "entry": round(entry, 2), "stop": stop, "target": target, "risk_reward": rr,
        "pivot": round(pivot, 2),
        "mid_bias": mid_bias, "mid_aligned": mid_aligned,
        "htf_lean": htf_lean, "conflicted": bool(caveats),
        "caveats": caveats,
        "note": note,
    }


def build(alpaca, symbol: str, config: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    settings = compression.settings_from_config(config or {})
    frames = _frames(alpaca, symbol)
    reads = {tf: _tf_read(frames.get(tf), settings) for tf in _TFS}
    reads = {tf: r for tf, r in reads.items() if r}
    watch = compression.watch(frames.get(_WATCH_TF), settings, _WATCH_TF)
    return {"symbol": symbol, "timeframes": reads,
            "watch": watch, "plan": _plan(reads, watch),
            "compression_tfs": list(_COMPRESSION_TFS), "watch_tf": _WATCH_TF,
            "alpaca_enabled": bool(getattr(alpaca, "enabled", False))}
