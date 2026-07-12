"""
Per-symbol timeframe-by-timeframe drill-down (the MAG-7 expand view).

Reads bias on 15m / 30m / 1h / 4h / daily (intraday from Alpaca, resampled for
30m/4h, daily from yfinance) and surfaces a trade plan ONLY when a genuine setup
exists -- Bollinger compression on 15m/30m/1h AND a MACD cross AND a pivot to
trade against. Direction comes from the cross + which pivot it resolves against
(bull cross holding above support -> long; bear cross failing at resistance ->
short). No trade is manufactured for a name that doesn't have the confluence;
bias is always shown, a plan only when it's really there.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd
import yfinance as yf

from src import indicators

_TFS = ["15m", "30m", "1h", "4h", "daily"]
_INTRADAY = ("15m", "30m", "1h")


def _resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    cols = [c for c in agg if c in df.columns]
    return df[cols].resample(rule).agg({c: agg[c] for c in cols}).dropna()


def _frames(alpaca, symbol: str) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    if alpaca and getattr(alpaca, "enabled", False):
        b15 = alpaca.bars([symbol], "15m", limit=400).get(symbol)
        b1h = alpaca.bars([symbol], "1h", limit=400).get(symbol)
        if b15 is not None and not b15.empty:
            frames["15m"] = b15
            frames["30m"] = _resample(b15, "30min")
        if b1h is not None and not b1h.empty:
            frames["1h"] = b1h
            frames["4h"] = _resample(b1h, "4h")
    try:
        d = yf.Ticker(symbol).history(period="1y", interval="1d", auto_adjust=True)
        if d is not None and not d.empty:
            frames["daily"] = d
    except Exception:
        pass
    return frames


def _tf_read(df: Optional[pd.DataFrame]) -> Optional[dict[str, Any]]:
    if df is None or len(df) < 30:
        return None
    closes = df["Close"]
    price = float(closes.iloc[-1])
    ph, pl = indicators.find_pivots(df, 3)
    struct = indicators.structure_bias(ph, pl)
    ema_up = bool(indicators.ema_alignment(closes, 9, 21, "up"))
    ema_dn = bool(indicators.ema_alignment(closes, 9, 21, "down"))
    macd = indicators.macd(closes)
    bb = indicators.bollinger_bands(closes)
    sig = macd["signal"]
    bull = struct == "BULLISH" or (ema_up and "BULL" in sig)
    bear = struct == "BEARISH" or (ema_dn and "BEAR" in sig)
    bias = "Bullish" if (bull and not bear) else "Bearish" if (bear and not bull) else "Neutral"
    return {
        "bias": bias,
        "macd": sig,
        "macd_cross": sig in ("BULLISH_CROSSOVER", "BEARISH_CROSSOVER"),
        "macd_dir": "up" if "BULL" in sig else "down" if "BEAR" in sig else "flat",
        "squeeze": bool(bb["squeeze"]),
        "support": indicators.nearest_level(pl, price, "below"),
        "resistance": indicators.nearest_level(ph, price, "above"),
        "price": round(price, 2),
    }


def _plan(reads: dict[str, dict[str, Any]]) -> Optional[dict[str, Any]]:
    """A plan only when the confluence is genuinely there."""
    # 1) compression on an intraday timeframe
    compressed = [tf for tf in _INTRADAY if reads.get(tf) and reads[tf]["squeeze"]]
    if not compressed:
        return None
    # 2) a MACD cross on an intraday timeframe, with a direction
    trigger = next((tf for tf in _INTRADAY
                    if reads.get(tf) and reads[tf]["macd_cross"] and reads[tf]["macd_dir"] in ("up", "down")), None)
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
    return {
        "direction": direction, "trigger_tf": trigger, "compressed_tfs": compressed,
        "entry": round(entry, 2), "stop": stop, "target": target, "risk_reward": rr,
        "pivot": round(pivot, 2),
        "note": (f"{'; '.join(compressed)} compression + {trigger} MACD {r['macd_dir']}-cross, "
                 f"{direction} against pivot {round(pivot, 2)}"),
    }


def build(alpaca, symbol: str) -> dict[str, Any]:
    frames = _frames(alpaca, symbol)
    reads = {tf: _tf_read(frames.get(tf)) for tf in _TFS}
    reads = {tf: r for tf, r in reads.items() if r}
    return {"symbol": symbol, "timeframes": reads, "plan": _plan(reads),
            "alpaca_enabled": bool(getattr(alpaca, "enabled", False))}
