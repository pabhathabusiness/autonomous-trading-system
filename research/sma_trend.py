"""SMA trend structure — daily-first, causal, per PREREGISTRATION.md § 4.

SMA set: 20, 50, 100, 200. Each SMA and its derived fields carry a
`_availability` flag. Below the preregistered minimum bars, fields return
None / "UNAVAILABLE" — never coerced to a neutral default.

No composite score. Each field is a separate observable dimension.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import math_utils as mu


FEATURE_VERSION = "v0.3.0"

# Preregistered SMA periods and their slope lookbacks (PREREGISTRATION § 4).
_SMA_SPEC = {
    20: 10,
    50: 20,
    100: 40,
    200: 80,
}

# Slope classification thresholds (fractional; identical across periods).
_RISING_TH = 0.01
_FALLING_TH = -0.01

# "Near" a level uses 0.5 · ATR14 across the module.
_NEAR_ATR_MULT = 0.5


# ------------------------------------------------------------------ primitives
def _sma(closes: pd.Series, period: int) -> pd.Series:
    return closes.rolling(period).mean()


def _slope_class(slope: float | None) -> str:
    if slope is None or not np.isfinite(slope):
        return "UNAVAILABLE"
    if slope >= _RISING_TH:
        return "RISING"
    if slope <= _FALLING_TH:
        return "FALLING"
    return "FLAT"


def _num(x: float) -> float | None:
    return float(x) if np.isfinite(x) else None


# ----------------------------------------------------------------- per-series
def sma_context_for_series(closes: pd.Series, highs_lows: pd.DataFrame | None,
                           *, atr14: float | None,
                           lookback_map: dict[int, int] | None = None) -> dict:
    """Compute SMA-context fields for a single close series aligned at bar t
    (last index of `closes` is t).

    `highs_lows` (a DataFrame with columns 'high','low','close') is passed
    for ATR when the caller doesn't already have it. If already provided
    via `atr14`, `highs_lows` may be None.

    Returns a flat dict of raw fields (unnamespaced). Callers add their own
    prefix (e.g. `trend.stock_` or `trend.spy_`).
    """
    lookback_map = lookback_map or _SMA_SPEC
    out: dict = {}
    if closes is None or closes.empty:
        for p in lookback_map:
            _fill_sma_unavailable(out, p)
        _fill_stack_unavailable(out)
        _fill_nearest_unavailable(out)
        return out

    price_t = float(closes.iloc[-1])
    n = len(closes)

    sma_values: dict[int, float | None] = {}
    for period, look in lookback_map.items():
        available = n >= period
        if available:
            sma_series = _sma(closes, period)
            sma_t = float(sma_series.iloc[-1]) if pd.notna(sma_series.iloc[-1]) else float("nan")
        else:
            sma_series = None
            sma_t = float("nan")

        sma_values[period] = float(sma_t) if np.isfinite(sma_t) else None

        # Level fields
        out[f"sma_{period}"] = _num(sma_t)
        out[f"sma_{period}_availability"] = bool(np.isfinite(sma_t))

        if np.isfinite(sma_t) and sma_t > 0:
            dist_pct = (price_t - sma_t) / sma_t
            out[f"distance_to_sma{period}_pct"] = float(dist_pct)
            if atr14 is not None and np.isfinite(atr14) and atr14 > 0:
                dist_atr = (price_t - sma_t) / atr14
                out[f"distance_to_sma{period}_atr"] = float(dist_atr)
                out[f"entry_near_sma{period}"] = bool(abs(dist_atr) <= _NEAR_ATR_MULT)
            else:
                out[f"distance_to_sma{period}_atr"] = None
                out[f"entry_near_sma{period}"] = None
            out[f"above_sma{period}"] = bool(price_t > sma_t)
        else:
            out[f"distance_to_sma{period}_pct"] = None
            out[f"distance_to_sma{period}_atr"] = None
            out[f"above_sma{period}"] = None
            out[f"entry_near_sma{period}"] = None

        # Slope + class (needs `period + look` bars)
        slope_ready = n >= (period + look) and sma_series is not None
        if slope_ready:
            sma_now = sma_series.iloc[-1]
            sma_back = sma_series.iloc[-look - 1]
            if pd.notna(sma_now) and pd.notna(sma_back) and sma_back > 0:
                slope = float(sma_now / sma_back - 1.0)
            else:
                slope = float("nan")
        else:
            slope = float("nan")
        out[f"sma_{period}_slope"] = _num(slope)
        out[f"sma_{period}_slope_lookback"] = int(look)
        out[f"sma_{period}_slope_class"] = _slope_class(slope if np.isfinite(slope) else None)
        out[f"sma_{period}_slope_availability"] = bool(np.isfinite(slope))

        # Reclaim / loss events (require at least `period + 1` bars)
        rl_ready = sma_series is not None and n >= (period + 1)
        if rl_ready:
            aligned = pd.DataFrame({"close": closes, "sma": sma_series}).dropna()
            if len(aligned) >= 2:
                events = _reclaim_loss_bars(aligned)
                bars_since_reclaim = _bars_since(events["reclaim"], len(aligned) - 1)
                bars_since_loss = _bars_since(events["loss"], len(aligned) - 1)
                out[f"bars_since_reclaim_sma{period}"] = bars_since_reclaim
                out[f"bars_since_loss_sma{period}"] = bars_since_loss
                out[f"holding_above_sma{period}_after_reclaim"] = _holding_since(
                    aligned, events["reclaim"], side="above"
                )
                out[f"holding_below_sma{period}_after_loss"] = _holding_since(
                    aligned, events["loss"], side="below"
                )
            else:
                out[f"bars_since_reclaim_sma{period}"] = None
                out[f"bars_since_loss_sma{period}"] = None
                out[f"holding_above_sma{period}_after_reclaim"] = None
                out[f"holding_below_sma{period}_after_loss"] = None
        else:
            out[f"bars_since_reclaim_sma{period}"] = None
            out[f"bars_since_loss_sma{period}"] = None
            out[f"holding_above_sma{period}_after_reclaim"] = None
            out[f"holding_below_sma{period}_after_loss"] = None

    # ---- Stack booleans (require adjacent SMAs)
    def _cmp(a: int, b: int) -> bool | None:
        va, vb = sma_values.get(a), sma_values.get(b)
        if va is None or vb is None:
            return None
        return va > vb

    out["sma20_gt_sma50"] = _cmp(20, 50)
    out["sma50_gt_sma100"] = _cmp(50, 100)
    out["sma100_gt_sma200"] = _cmp(100, 200)

    stack_bits = [out["sma20_gt_sma50"], out["sma50_gt_sma100"], out["sma100_gt_sma200"]]
    if any(x is None for x in stack_bits):
        out["bullish_full_stack"] = None
        out["bearish_full_stack"] = None
        out["sma_stack_state"] = "UNAVAILABLE"
    else:
        out["bullish_full_stack"] = bool(all(stack_bits))
        out["bearish_full_stack"] = bool(all(not b for b in stack_bits))
        if out["bullish_full_stack"]:
            out["sma_stack_state"] = "BULLISH_STACK"
        elif out["bearish_full_stack"]:
            out["sma_stack_state"] = "BEARISH_STACK"
        else:
            out["sma_stack_state"] = "MIXED"

    # ---- Nearest SMA proximity
    available_pairs = [(p, sma_values[p]) for p in lookback_map if sma_values[p] is not None]
    if not available_pairs:
        _fill_nearest_unavailable(out)
    else:
        nearest_period, nearest_val = min(available_pairs, key=lambda kv: abs(price_t - kv[1]))
        out["nearest_sma_period"] = int(nearest_period)
        out["nearest_sma_value"] = float(nearest_val)
        out["nearest_sma_distance_pct"] = (price_t - nearest_val) / nearest_val if nearest_val > 0 else None
        if atr14 is not None and np.isfinite(atr14) and atr14 > 0:
            out["nearest_sma_distance_atr"] = float((price_t - nearest_val) / atr14)
        else:
            out["nearest_sma_distance_atr"] = None

    return out


def _fill_sma_unavailable(out: dict, period: int) -> None:
    out[f"sma_{period}"] = None
    out[f"sma_{period}_availability"] = False
    out[f"distance_to_sma{period}_pct"] = None
    out[f"distance_to_sma{period}_atr"] = None
    out[f"above_sma{period}"] = None
    out[f"entry_near_sma{period}"] = None
    out[f"sma_{period}_slope"] = None
    out[f"sma_{period}_slope_lookback"] = _SMA_SPEC.get(period)
    out[f"sma_{period}_slope_class"] = "UNAVAILABLE"
    out[f"sma_{period}_slope_availability"] = False
    out[f"bars_since_reclaim_sma{period}"] = None
    out[f"bars_since_loss_sma{period}"] = None
    out[f"holding_above_sma{period}_after_reclaim"] = None
    out[f"holding_below_sma{period}_after_loss"] = None


def _fill_stack_unavailable(out: dict) -> None:
    out["sma20_gt_sma50"] = None
    out["sma50_gt_sma100"] = None
    out["sma100_gt_sma200"] = None
    out["bullish_full_stack"] = None
    out["bearish_full_stack"] = None
    out["sma_stack_state"] = "UNAVAILABLE"


def _fill_nearest_unavailable(out: dict) -> None:
    out["nearest_sma_period"] = None
    out["nearest_sma_value"] = None
    out["nearest_sma_distance_pct"] = None
    out["nearest_sma_distance_atr"] = None


def _reclaim_loss_bars(aligned: pd.DataFrame, max_lookback: int = 250) -> dict[str, list[int]]:
    """Return dict of iloc positions where reclaim / loss events occurred
    within trailing `max_lookback` bars."""
    tail = aligned.tail(max_lookback)
    close = tail["close"].to_numpy()
    sma = tail["sma"].to_numpy()
    reclaim = []
    loss = []
    for i in range(1, len(tail)):
        if close[i - 1] <= sma[i - 1] and close[i] > sma[i]:
            reclaim.append(i)
        if close[i - 1] >= sma[i - 1] and close[i] < sma[i]:
            loss.append(i)
    return {"reclaim": reclaim, "loss": loss}


def _bars_since(events: list[int], last_iloc: int) -> int | None:
    if not events:
        return None
    return int(last_iloc - events[-1])


def _holding_since(aligned: pd.DataFrame, events: list[int], side: str) -> bool | None:
    """After the most recent event, has every close stayed on the intended
    side of its SMA at close? None if no event in window."""
    if not events:
        return None
    tail = aligned.tail(250)
    ev = events[-1]
    slc = tail.iloc[ev:]
    if slc.empty:
        return None
    if side == "above":
        return bool((slc["close"] >= slc["sma"]).all())
    return bool((slc["close"] <= slc["sma"]).all())


# ------------------------------------------------------------- public entry
def context_at(stock_df: pd.DataFrame, spy_df: pd.DataFrame | None, t: int,
               *, spy_t: pd.Timestamp | None = None) -> dict:
    """Compute SMA context for the stock (and, if provided, SPY) at bar t.

    `stock_df` must have columns ['open','high','low','close']. `spy_df` may
    be None (no SPY comparison fields).

    Returns a flat dict with `trend.stock_*`, `trend.spy_*`, and
    `trend.derived_*` prefixes.
    """
    if t < 0 or t >= len(stock_df):
        raise IndexError(f"t={t} out of range for stock_df of length {len(stock_df)}")
    hist = stock_df.iloc[: t + 1]
    atr = mu.atr(hist, 14)
    atr_t = float(atr.iloc[-1]) if len(atr) and pd.notna(atr.iloc[-1]) else float("nan")

    stock_ctx = sma_context_for_series(hist["close"], hist, atr14=atr_t if np.isfinite(atr_t) else None)

    out: dict = {"trend._feature_version": FEATURE_VERSION,
                 "trend._source_timeframe": "1d",
                 "trend._known_at": hist.index[-1].isoformat()}
    for k, v in stock_ctx.items():
        out[f"trend.stock_{k}"] = v

    if spy_df is not None and not spy_df.empty:
        anchor = spy_t if spy_t is not None else hist.index[-1]
        spy_hist = spy_df[spy_df.index <= anchor]
        if not spy_hist.empty:
            spy_atr = mu.atr(spy_hist, 14)
            spy_atr_t = float(spy_atr.iloc[-1]) if len(spy_atr) and pd.notna(spy_atr.iloc[-1]) else float("nan")
            spy_ctx = sma_context_for_series(
                spy_hist["close"] if "close" in spy_hist.columns else spy_hist.iloc[:, 0],
                spy_hist,
                atr14=spy_atr_t if np.isfinite(spy_atr_t) else None,
            )
        else:
            spy_ctx = sma_context_for_series(pd.Series(dtype=float), None, atr14=None)
        for k, v in spy_ctx.items():
            out[f"trend.spy_{k}"] = v

        out["trend.derived_stock_above_sma50_spy_below_sma50"] = _pair_and(
            out.get("trend.stock_above_sma50"), _not(out.get("trend.spy_above_sma50")))
        out["trend.derived_stock_above_sma200_spy_below_sma200"] = _pair_and(
            out.get("trend.stock_above_sma200"), _not(out.get("trend.spy_above_sma200")))
        out["trend.derived_stock_sma50_rising_spy_sma50_falling"] = _class_pair(
            out.get("trend.stock_sma_50_slope_class"),
            "RISING",
            out.get("trend.spy_sma_50_slope_class"),
            "FALLING",
        )
        out["trend.derived_stock_bullish_stack_spy_not_bullish_stack"] = _pair_and(
            out.get("trend.stock_bullish_full_stack"),
            _not(out.get("trend.spy_bullish_full_stack")),
        )
    else:
        out["trend.derived_stock_above_sma50_spy_below_sma50"] = None
        out["trend.derived_stock_above_sma200_spy_below_sma200"] = None
        out["trend.derived_stock_sma50_rising_spy_sma50_falling"] = None
        out["trend.derived_stock_bullish_stack_spy_not_bullish_stack"] = None

    return out


def _not(x: bool | None) -> bool | None:
    if x is None:
        return None
    return not x


def _pair_and(a: bool | None, b: bool | None) -> bool | None:
    if a is None or b is None:
        return None
    return bool(a and b)


def _class_pair(a: str | None, want_a: str, b: str | None, want_b: str) -> bool | None:
    if a is None or b is None:
        return None
    if a == "UNAVAILABLE" or b == "UNAVAILABLE":
        return None
    return bool(a == want_a and b == want_b)
