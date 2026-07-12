"""
Addendum 2 -- small-cap signal library, the KEY-INDEPENDENT half.

Everything here is computed from daily OHLCV (+ split history) via the existing
yfinance source -- NO Finnhub. The Finnhub-gated pieces (float, filings/dilution,
going-concern, fundamentals, price-target, options) live elsewhere and stay
dormant until FINNHUB_KEY is set and the free-tier probe confirms availability.

Pure compute functions take DataFrames so they unit-test with no network. rel_vol
is v1 DAILY per spec (full-day volume vs 20d avg) -- honest + free; labeled as
such. Direction is never predicted in a squeeze; the trigger is the expansion.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pandas as pd

_BOTTOM_DECILE = 10.0   # "compressed" = bb_width in bottom decile of its own 120d
_EXTREME = 5.0          # compression_extreme threshold


def _bb_width_series(closes: pd.Series, period: int = 20, num_std: float = 2.0) -> pd.Series:
    mid = closes.rolling(period).mean()
    std = closes.rolling(period).std()
    return ((mid + num_std * std) - (mid - num_std * std)) / mid.replace(0, pd.NA)


def compute_ohlc_signals(daily: pd.DataFrame) -> Optional[dict[str, Any]]:
    """Daily-OHLC signals for one symbol. None when there isn't enough history."""
    if daily is None or daily.empty or len(daily) < 30:
        return None
    closes, highs, lows, vols = daily["Close"], daily["High"], daily["Low"], daily["Volume"]
    price = float(closes.iloc[-1])

    # rel_vol v1 (daily): today's full-day volume vs trailing 20d average
    avg20 = float(vols.iloc[-21:-1].mean()) if len(vols) > 21 else float(vols.mean())
    rel_vol = round(float(vols.iloc[-1]) / avg20, 2) if avg20 > 0 else None
    avg_dollar_vol_20d = round(float((closes.iloc[-20:] * vols.iloc[-20:]).mean()), 0)

    # Bollinger compression, ranked against THIS name's own trailing 120d width
    width = _bb_width_series(closes).dropna()
    bb_pct = daily_comp = comp_extreme = squeeze_days = None
    if len(width) >= 20:
        window = width.tail(120)
        today = width.iloc[-1]
        bb_pct = round(100.0 * float((window <= today).sum()) / len(window), 1)
        daily_comp = bb_pct <= _BOTTOM_DECILE
        # consecutive recent days in the bottom decile (each ranked in its own window)
        streak = 0
        for i in range(len(width) - 1, max(-1, len(width) - 130), -1):
            w = width.iloc[max(0, i - 119): i + 1]
            if len(w) < 20:
                break
            pctl = 100.0 * float((w <= width.iloc[i]).sum()) / len(w)
            if pctl <= _BOTTOM_DECILE:
                streak += 1
            else:
                break
        squeeze_days = streak
        comp_extreme = bool(bb_pct <= _EXTREME and streak >= 5)

    # weekly trend: up week-over-week + consecutive up weeks
    wk = closes.resample("W-FRI").last().dropna()
    up_wow = consec = None
    if len(wk) >= 2:
        up_wow = bool(wk.iloc[-1] > wk.iloc[-2])
        consec = 0
        for a, b in zip(wk.iloc[::-1], wk.iloc[::-1].shift(-1)):
            if pd.notna(b) and a > b:
                consec += 1
            else:
                break

    # sub-$1 delisting streak (consecutive most-recent closes < $1)
    sub_dollar_streak = 0
    for c in closes.iloc[::-1]:
        if c < 1.0:
            sub_dollar_streak += 1
        else:
            break

    return {
        "price": round(price, 4),
        "rel_vol": rel_vol,
        "rel_vol_basis": "daily_v1",     # honest label per spec
        "avg_dollar_vol_20d": avg_dollar_vol_20d,
        "bb_percentile": bb_pct,
        "daily_compression": bool(daily_comp) if daily_comp is not None else None,
        "compression_extreme": comp_extreme,
        "squeeze_days": squeeze_days,
        "up_wow": up_wow,
        "consecutive_up_weeks": consec,
        "sub_dollar_streak": sub_dollar_streak,
    }


def reverse_split_flags(splits: Optional[pd.Series], asof: Optional[datetime] = None) -> dict[str, Any]:
    """From yfinance split history: reverse (< 1.0 ratio) split within 18 months,
    and count over the last 5 years (>= 2 => serial compliance-splitter)."""
    asof = asof or datetime.now(timezone.utc)
    out = {"reverse_18mo": False, "reverse_count_5y": 0, "serial_reverse": False}
    if splits is None or len(splits) == 0:
        return out
    for ts, ratio in splits.items():
        try:
            dt = pd.Timestamp(ts).to_pydatetime()
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if ratio >= 1.0:            # forward split, irrelevant
            continue
        age_days = (asof - dt).days
        if 0 <= age_days <= 5 * 365:
            out["reverse_count_5y"] += 1
        if 0 <= age_days <= 548:    # ~18 months
            out["reverse_18mo"] = True
    out["serial_reverse"] = out["reverse_count_5y"] >= 2
    return out


def deathwatch_ohlc(daily: pd.DataFrame, splits: Optional[pd.Series],
                    asof: Optional[datetime] = None) -> Optional[tuple[str, str]]:
    """HARD deathwatch derivable WITHOUT Finnhub. Addendum 3 1.4: reverse-split
    (a, b) stay HARD -- those catch the zombies. The sub-$1 rule (e) is NO LONGER
    a hard exclusion here (it banned the sub-$1 tiers the user wants); it becomes
    a scored -1.5 DELISTING-RISK penalty in the lane engine instead. Criteria c
    (going-concern) and d (share treadmill) live in the Finnhub layer."""
    rs = reverse_split_flags(splits, asof)
    if rs["serial_reverse"]:
        return ("serial_reverse_split", f"{rs['reverse_count_5y']} reverse splits in 5y (permanent)")
    if rs["reverse_18mo"]:
        return ("reverse_split_18mo", "reverse split within 18 months")
    return None
