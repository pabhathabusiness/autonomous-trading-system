"""
Bollinger compression the way it actually pays: the UNUSUAL kind.

Ordinary "the bands look narrow" is not an edge -- a quartile-of-60-bars test
fires a quarter of the time by construction, which is why the old squeeze flag
tagged every quiet stretch as a setup. Real compression is rarer and has three
measurable fingerprints, and this module demands all three at once:

  1. BANDWIDTH PERCENTILE -- current band width ranked against a long lookback
     (default 120 bars). "Lowest 10% for this name" travels across symbols and
     price levels in a way a raw width never does.
  2. BB INSIDE KELTNER (the TTM squeeze) -- standard-deviation width collapsing
     inside ATR width means realised volatility has dropped relative to the
     recent trading range. Bandwidth alone can look low in a slow drift; this
     is the condition that says energy is actually being stored.
  3. DURATION -- consecutive bars in compression. A one-bar lull is noise; a
     coil that has held for many bars is the one that snaps.

Direction is deliberately NOT taken from the squeeze. Compression is a TIMING
signal -- it says a move is coming, not which way. Direction comes from the
break of the upper/lower band, with the middle band (the basis) supplying bias:
price holding above a rising basis is a different animal from price bleeding
under a falling one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import pandas as pd

from src import indicators

GRADES = ("none", "mild", "tight", "extreme")


@dataclass(frozen=True)
class Settings:
    """Thresholds for what counts as compression. Tunable from config so the
    backtest (tools/backtest_compression.py) can drive them empirically rather
    than leaving them at hand-picked guesses."""
    period: int = 20
    num_std: float = 2.0
    lookback: int = 250           # bars the bandwidth percentile ranks against
    min_rank_bars: int = 60       # refuse to rank against less history than this
    keltner_mult: float = 1.5     # ATR multiple for the Keltner channel
    extreme_pctile: float = 5.0
    tight_pctile: float = 10.0
    mild_pctile: float = 20.0
    min_squeeze_bars: int = 3     # a coil must hold this long to count
    require_keltner: bool = True  # demand the TTM condition, not just narrow bands
    mid_slope_bars: int = 5       # basis slope measured over this many bars
    mid_test_bars: int = 6        # window for spotting a basis test/reclaim


def settings_from_config(config: dict[str, Any]) -> Settings:
    tcfg = (config or {}).get("technical", {})
    ccfg = tcfg.get("compression", {}) or {}
    return Settings(
        period=tcfg.get("bollinger_period", 20),
        num_std=tcfg.get("bollinger_std", 2.0),
        lookback=ccfg.get("lookback_bars", 250),
        min_rank_bars=ccfg.get("min_rank_bars", 60),
        keltner_mult=ccfg.get("keltner_atr_mult", 1.5),
        extreme_pctile=ccfg.get("extreme_pctile", 5.0),
        tight_pctile=ccfg.get("tight_pctile", 10.0),
        mild_pctile=ccfg.get("mild_pctile", 20.0),
        min_squeeze_bars=ccfg.get("min_squeeze_bars", 3),
        require_keltner=ccfg.get("require_keltner", True),
        mid_slope_bars=ccfg.get("mid_slope_bars", 5),
        mid_test_bars=ccfg.get("mid_test_bars", 6),
    )


def _grade(pctile: Optional[float], s: Settings) -> str:
    if pctile is None:
        return "none"
    if pctile <= s.extreme_pctile:
        return "extreme"
    if pctile <= s.tight_pctile:
        return "tight"
    if pctile <= s.mild_pctile:
        return "mild"
    return "none"


def _trailing_run(flags: pd.Series) -> int:
    """Consecutive True values at the tail of a boolean series."""
    run = 0
    for flag in reversed(flags.fillna(False).tolist()):
        if not flag:
            break
        run += 1
    return run


def _mid_band(df: pd.DataFrame, middle: pd.Series, s: Settings) -> dict[str, Any]:
    """How price is interacting with the basis (middle band), and the bias that
    interaction implies.

    The middle band is a 20-period mean, so it doubles as the short-term trend
    line. What matters is not merely which side price sits on but whether the
    basis is sloping with it, and whether a recent touch was defended (support
    held) or sold (resistance rejected).
    """
    closes = df["Close"]
    price = float(closes.iloc[-1])
    mid = middle.iloc[-1]
    if pd.isna(mid) or mid == 0:
        return {"pos": None, "slope": None, "bias": "neutral", "test": None,
                "distance_pct": None, "middle": None, "note": "no basis yet"}

    mid = float(mid)
    distance_pct = (price - mid) / mid * 100.0
    pos = "at" if abs(distance_pct) < 0.1 else ("above" if distance_pct > 0 else "below")

    slope = "flat"
    if len(middle.dropna()) > s.mid_slope_bars:
        past = middle.iloc[-1 - s.mid_slope_bars]
        if pd.notna(past) and past != 0:
            change = (mid - float(past)) / float(past) * 100.0
            slope = "rising" if change > 0.05 else "falling" if change < -0.05 else "flat"

    # Did price cross the basis inside the window, or test and respect it?
    test = None
    window = min(s.mid_test_bars, len(df) - 1)
    if window > 0:
        prev_close, prev_mid = closes.iloc[-1 - window], middle.iloc[-1 - window]
        if pd.notna(prev_mid):
            crossed_up = float(prev_close) < float(prev_mid) and price > mid
            crossed_down = float(prev_close) > float(prev_mid) and price < mid
            recent, recent_mid = df.iloc[-window:], middle.iloc[-window:]
            if crossed_up:
                test = "reclaimed"
            elif crossed_down:
                test = "lost"
            elif pos == "above" and (recent["Low"] <= recent_mid).any():
                test = "held"       # dipped into the basis and closed back above
            elif pos == "below" and (recent["High"] >= recent_mid).any():
                test = "rejected"   # poked at the basis and got sold

    if test == "reclaimed":
        bias = "bullish"
    elif test == "lost":
        bias = "bearish"
    elif pos == "above" and slope == "rising":
        bias = "bullish"
    elif pos == "below" and slope == "falling":
        bias = "bearish"
    elif test == "held":
        bias = "bullish"
    elif test == "rejected":
        bias = "bearish"
    else:
        bias = "neutral"

    notes = {
        "reclaimed": "reclaimed the basis from below",
        "lost": "lost the basis from above",
        "held": "basis held as support on a dip",
        "rejected": "basis rejected price from below",
    }
    note = notes.get(test) or f"{pos} a {slope} basis"
    return {"pos": pos, "slope": slope, "bias": bias, "test": test,
            "distance_pct": round(distance_pct, 2), "middle": round(mid, 2),
            "note": note}


def analyze(df: Optional[pd.DataFrame], s: Optional[Settings] = None) -> Optional[dict[str, Any]]:
    """Full compression read for one timeframe. None when there aren't enough
    bars to rank bandwidth honestly (a percentile off 20 bars is meaningless)."""
    s = s or Settings()
    if df is None or "Close" not in df or len(df) < s.period + s.min_rank_bars:
        return None

    closes = df["Close"]
    bb_upper, bb_mid, bb_lower = indicators.bollinger_series(closes, s.period, s.num_std)
    k_upper, _, k_lower = indicators.keltner_series(df, s.period, s.keltner_mult, s.period)

    # np.nan (not pd.NA) keeps the series float64 -- pd.NA upcasts to object on
    # pandas 2.x, which quietly breaks the rolling quantiles below
    width = (bb_upper - bb_lower) / bb_mid.replace(0, np.nan)
    current_width = width.iloc[-1]
    history = width.tail(s.lookback)
    if history.dropna().shape[0] < s.min_rank_bars or pd.isna(current_width):
        return None

    pctile = indicators.percentile_rank(history, float(current_width))
    grade = _grade(pctile, s)

    # TTM squeeze: both Bollinger bands sitting inside the Keltner channel.
    inside = ((bb_upper < k_upper) & (bb_lower > k_lower)).fillna(False)
    ttm_squeeze = bool(inside.iloc[-1])

    # Duration comes off the TTM condition, not off a bandwidth percentile.
    # A percentile threshold is self-referential once a coil runs long: the
    # coil's own bars populate the low end of the lookback, so the threshold
    # sinks beneath the very bars it should be counting and the run resets to
    # zero. BB-inside-Keltner has no such feedback -- standard deviation
    # collapses faster than ATR in a real coil, so the flag simply stays on.
    threshold = float(history.quantile(s.tight_pctile / 100.0))
    bars_in_squeeze = _trailing_run(inside) if ttm_squeeze else _trailing_run(width <= threshold)

    price = float(closes.iloc[-1])
    upper, lower, middle = float(bb_upper.iloc[-1]), float(bb_lower.iloc[-1]), float(bb_mid.iloc[-1])
    percent_b = (price - lower) / (upper - lower) if upper != lower else 0.5
    position = ("NEAR_LOWER" if percent_b <= 0.15
                else "NEAR_UPPER" if percent_b >= 0.85 else "MIDDLE")

    unusual = bool(
        grade in ("tight", "extreme")
        and bars_in_squeeze >= s.min_squeeze_bars
        and (ttm_squeeze or not s.require_keltner)
    )

    mid = _mid_band(df, bb_mid, s)
    label = (f"{grade} · BBW {pctile:.0f}th pct · {bars_in_squeeze} bars"
             + (" · BB inside Keltner" if ttm_squeeze else "")) if pctile is not None else grade

    return {
        "grade": grade,
        "unusual": unusual,
        "bandwidth": round(float(current_width), 5),
        "bandwidth_pctile": round(pctile, 1) if pctile is not None else None,
        "ttm_squeeze": ttm_squeeze,
        "bars_in_squeeze": int(bars_in_squeeze),
        "upper": round(upper, 2), "lower": round(lower, 2), "middle": round(middle, 2),
        "price": round(price, 2),
        "percent_b": round(percent_b, 3), "position": position,
        "break_up": bool(price > upper),
        "break_down": bool(price < lower),
        "mid": mid,
        "label": label,
    }


def watch(df: Optional[pd.DataFrame], s: Optional[Settings] = None,
          timeframe: str = "4h") -> Optional[dict[str, Any]]:
    """The higher-timeframe watch state -- computed, then held as a trigger to
    wait for rather than a trade to take.

    A 4h coil is too slow to time an entry off, but it is the frame that says
    how much fuel the eventual move has. So it is reported as armed/triggered
    with the exact band levels to watch, and the basis supplies the lean.
    """
    c = analyze(df, s)
    if not c:
        return None

    if c["break_up"]:
        state = "triggered_up"
    elif c["break_down"]:
        state = "triggered_down"
    elif c["unusual"]:
        state = "armed"
    elif c["grade"] != "none":
        state = "coiling"
    else:
        state = "idle"

    bias = c["mid"]["bias"]
    lean = "long" if bias == "bullish" else "short" if bias == "bearish" else None

    if state == "triggered_up":
        note = f"{timeframe} broke the upper band ({c['upper']}) — expansion under way"
    elif state == "triggered_down":
        note = f"{timeframe} broke the lower band ({c['lower']}) — expansion under way"
    elif state == "armed":
        note = (f"{timeframe} coiled ({c['grade']}, {c['bars_in_squeeze']} bars) — "
                f"watch for a break of {c['upper']} up / {c['lower']} down; "
                f"basis bias {bias} ({c['mid']['note']})")
    elif state == "coiling":
        note = (f"{timeframe} narrowing ({c['grade']}, BBW {c['bandwidth_pctile']}th pct) — "
                f"not unusual enough to arm yet")
    else:
        note = f"{timeframe} bands are normal — nothing coiled"

    return {"state": state, "lean": lean, "note": note, "timeframe": timeframe, **c}
