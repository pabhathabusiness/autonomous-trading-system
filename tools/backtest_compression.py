#!/usr/bin/env python3
"""
Which KIND of Bollinger compression actually precedes a big move?

The live system now demands "unusual" compression (src/compression.py), and the
thresholds behind that word should be measured, not guessed. This walks history
bar by bar, finds every compression episode, tags it by grade / duration /
BB-inside-Keltner / basis bias, then measures what price did AFTERWARDS -- and
compares that to the base rate, because a 55% hit rate is worthless if plain
bars do 54%.

Everything is point-in-time. Bandwidth at bar i is ranked only against the
window ending at bar i, so no episode is graded with information that did not
exist when it was forming.

Run it on the server (this needs Yahoo data):

    cd /home/trading/autonomous-trading-system
    .venv/bin/python tools/backtest_compression.py --timeframe 1d --horizon 20
    .venv/bin/python tools/backtest_compression.py --timeframe 1h --period 2y --horizon 12
    .venv/bin/python tools/backtest_compression.py --timeframe 15m --period 60d --horizon 26

Read the LIFT column: 1.0 means that flavour of compression is no better than a
coin flip on a random bar. Set config technical.compression thresholds to the
tightest bucket that still holds a workable sample (n >= ~100).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import Any, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import indicators  # noqa: E402

# yfinance caps intraday history; asking for more silently returns less
_MAX_PERIOD = {"15m": "60d", "30m": "60d", "1h": "730d", "1d": "max", "1wk": "max"}
_DURATION_BUCKETS = [(1, 4, "1-4"), (5, 9, "5-9"), (10, 19, "10-19"), (20, 10**6, "20+")]


def _bucket(bars: int) -> str:
    for lo, hi, label in _DURATION_BUCKETS:
        if lo <= bars <= hi:
            return label
    return "?"


def load_bars(symbol: str, timeframe: str, period: str) -> Optional[pd.DataFrame]:
    import yfinance as yf
    try:
        df = yf.Ticker(symbol).history(period=period, interval=timeframe, auto_adjust=True)
    except Exception as exc:
        print(f"  ! {symbol}: {exc}", file=sys.stderr)
        return None
    if df is None or df.empty:
        return None
    df = df.dropna()
    return df if len(df) > 120 else None


def compression_frame(df: pd.DataFrame, period: int, num_std: float, lookback: int,
                      keltner_mult: float) -> pd.DataFrame:
    """Per-bar compression state, computed strictly from trailing data."""
    closes = df["Close"]
    bb_up, bb_mid, bb_lo = indicators.bollinger_series(closes, period, num_std)
    k_up, _, k_lo = indicators.keltner_series(df, period, keltner_mult, period)
    # np.nan keeps this float64; pd.NA would upcast to object on pandas 2.x
    width = (bb_up - bb_lo) / bb_mid.replace(0, np.nan)

    out = pd.DataFrame(index=df.index)
    out["width"] = width
    # trailing quantiles -- "at or below the Nth percentile of its own history"
    for name, pct in (("q5", 0.05), ("q10", 0.10), ("q20", 0.20)):
        out[name] = width.rolling(lookback, min_periods=60).quantile(pct)
    out["ttm"] = ((bb_up < k_up) & (bb_lo > k_lo)).fillna(False)
    out["upper"], out["middle"], out["lower"] = bb_up, bb_mid, bb_lo
    out["atr"] = indicators.atr_series(df, 14)
    # basis bias, vectorised: side of the middle band + slope of the middle band
    slope = bb_mid.pct_change(5)
    above = closes > bb_mid
    out["mid_bias"] = "neutral"
    out.loc[above & (slope > 0.0005), "mid_bias"] = "bullish"
    out.loc[(~above) & (slope < -0.0005), "mid_bias"] = "bearish"
    return out


def forward_stats(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Excursions over the NEXT `horizon` bars (bar i+1 .. i+horizon)."""
    fwd = pd.DataFrame(index=df.index)
    fwd["high"] = df["High"].rolling(horizon, min_periods=horizon).max().shift(-horizon)
    fwd["low"] = df["Low"].rolling(horizon, min_periods=horizon).min().shift(-horizon)
    fwd["close"] = df["Close"].shift(-horizon)
    return fwd


def _measure(close: float, atr: float, fwd_high: float, fwd_low: float,
             fwd_close: float, big_move_atr: float) -> Optional[dict[str, Any]]:
    if not atr or atr <= 0 or pd.isna(fwd_high) or pd.isna(fwd_low) or pd.isna(fwd_close):
        return None
    up_atr = (fwd_high - close) / atr
    dn_atr = (close - fwd_low) / atr
    return {
        "up_atr": float(up_atr), "dn_atr": float(dn_atr),
        "max_atr": float(max(up_atr, dn_atr)),
        "big": bool(max(up_atr, dn_atr) >= big_move_atr),
        "direction": "up" if up_atr >= dn_atr else "down",
        "net_pct": float((fwd_close - close) / close * 100.0),
        "mfe_pct": float((fwd_high - close) / close * 100.0),
        "mae_pct": float((fwd_low - close) / close * 100.0),
    }


def collect(df: pd.DataFrame, comp: pd.DataFrame, fwd: pd.DataFrame,
            horizon: int, big_move_atr: float, min_bars: int) -> tuple[list, list]:
    """Compression episodes (measured from their RELEASE bar) + the base rate
    sample (every bar with complete forward data)."""
    closes = df["Close"].to_numpy(dtype=float)
    atr = comp["atr"].to_numpy(dtype=float)
    width = comp["width"].to_numpy(dtype=float)
    q5, q10, q20 = (comp[c].to_numpy(dtype=float) for c in ("q5", "q10", "q20"))
    ttm = comp["ttm"].to_numpy(dtype=bool)
    mid_bias = comp["mid_bias"].to_numpy()
    upper, lower = comp["upper"].to_numpy(dtype=float), comp["lower"].to_numpy(dtype=float)
    f_high, f_low, f_close = (fwd[c].to_numpy(dtype=float) for c in ("high", "low", "close"))
    n = len(df)

    baseline: list[dict[str, Any]] = []
    for i in range(n):
        m = _measure(closes[i], atr[i], f_high[i], f_low[i], f_close[i], big_move_atr)
        if m:
            baseline.append(m)

    # an episode is a maximal run of bars whose width sits in the lowest 20% of
    # its own trailing window; grade/ttm are read at the LAST bar of the run
    compressed = (width <= q20)
    episodes: list[dict[str, Any]] = []
    i = 0
    while i < n:
        if not compressed[i] or pd.isna(q20[i]):
            i += 1
            continue
        start = i
        while i + 1 < n and compressed[i + 1]:
            i += 1
        end = i           # last compressed bar
        i += 1
        bars = end - start + 1
        if bars < min_bars:
            continue
        w, c = width[end], closes[end]
        if pd.isna(w) or pd.isna(q5[end]):
            continue
        grade = "extreme" if w <= q5[end] else "tight" if w <= q10[end] else "mild"
        m = _measure(c, atr[end], f_high[end], f_low[end], f_close[end], big_move_atr)
        if not m:
            continue
        episodes.append({
            **m, "grade": grade, "bars": bars, "bucket": _bucket(bars),
            "ttm": bool(ttm[end]), "mid_bias": str(mid_bias[end]),
            "at_upper": bool(c >= upper[end]), "at_lower": bool(c <= lower[end]),
        })
    return episodes, baseline


def _rate(rows: list[dict[str, Any]]) -> float:
    return sum(r["big"] for r in rows) / len(rows) if rows else 0.0


def _median(rows: list[dict[str, Any]], key: str) -> float:
    return float(pd.Series([r[key] for r in rows]).median()) if rows else 0.0


def _table(title: str, groups: dict[Any, list], base: float, min_n: int,
           label_fn=lambda k: str(k)) -> list[dict[str, Any]]:
    print(f"\n{title}")
    print(f"  {'bucket':<34}{'n':>7}{'big-move':>10}{'lift':>8}"
          f"{'med |mv|':>10}{'med MFE':>9}{'med MAE':>9}{'up:dn':>10}")
    print("  " + "-" * 97)
    out = []
    for key, rows in sorted(groups.items(), key=lambda kv: -_rate(kv[1])):
        if len(rows) < min_n:
            continue
        rate = _rate(rows)
        ups = sum(r["direction"] == "up" for r in rows)
        row = {"bucket": label_fn(key), "n": len(rows), "big_move_rate": round(rate, 4),
               "lift": round(rate / base, 2) if base else None,
               "median_max_atr": round(_median(rows, "max_atr"), 2),
               "median_mfe_pct": round(_median(rows, "mfe_pct"), 2),
               "median_mae_pct": round(_median(rows, "mae_pct"), 2),
               "up_pct": round(ups / len(rows) * 100, 1)}
        out.append(row)
        print(f"  {row['bucket']:<34}{row['n']:>7}{rate:>9.1%}"
              f"{(rate / base if base else 0):>8.2f}{row['median_max_atr']:>10.2f}"
              f"{row['median_mfe_pct']:>8.1f}%{row['median_mae_pct']:>8.1f}%"
              f"{ups / len(rows) * 100:>7.0f}:{100 - ups / len(rows) * 100:<3.0f}")
    if not out:
        print("  (no bucket met the minimum sample size)")
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbols", nargs="*", help="explicit tickers (default: config/universe.json)")
    p.add_argument("--timeframe", default="1d", choices=list(_MAX_PERIOD))
    p.add_argument("--period", default=None, help="history to pull (default: max for the timeframe)")
    p.add_argument("--horizon", type=int, default=20, help="bars measured after release")
    p.add_argument("--big-move-atr", type=float, default=3.0,
                   help="a 'big move' is an excursion >= this many ATR (default 3)")
    p.add_argument("--lookback", type=int, default=250, help="bars the bandwidth ranks against")
    p.add_argument("--bb-period", type=int, default=20)
    p.add_argument("--bb-std", type=float, default=2.0)
    p.add_argument("--keltner-mult", type=float, default=1.5)
    p.add_argument("--min-episode-bars", type=int, default=1)
    p.add_argument("--min-sample", type=int, default=30, help="hide buckets thinner than this")
    p.add_argument("--limit", type=int, default=0, help="cap symbols (0 = no cap)")
    p.add_argument("--json", dest="json_out", help="write the full result to this path")
    args = p.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    symbols = args.symbols
    if not symbols:
        with open(os.path.join(root, "config", "universe.json")) as fh:
            universe = json.load(fh)
        seen: list[str] = []
        for sector in universe.get("sectors", []):
            for sym in sector.get("candidates", []):
                if sym not in seen:
                    seen.append(sym)
        symbols = seen
    if args.limit:
        symbols = symbols[:args.limit]
    period = args.period or _MAX_PERIOD[args.timeframe]

    print(f"Compression backtest · {args.timeframe} bars · {period} history · "
          f"{len(symbols)} symbols")
    print(f"Big move = excursion >= {args.big_move_atr} ATR within {args.horizon} bars "
          f"of the squeeze releasing")

    episodes: list[dict[str, Any]] = []
    baseline: list[dict[str, Any]] = []
    used = 0
    for idx, sym in enumerate(symbols, 1):
        df = load_bars(sym, args.timeframe, period)
        if df is None:
            continue
        comp = compression_frame(df, args.bb_period, args.bb_std, args.lookback,
                                 args.keltner_mult)
        fwd = forward_stats(df, args.horizon)
        eps, base = collect(df, comp, fwd, args.horizon, args.big_move_atr,
                            args.min_episode_bars)
        episodes.extend(eps)
        baseline.extend(base)
        used += 1
        print(f"\r  loaded {idx}/{len(symbols)} ({used} usable, {len(episodes)} episodes)",
              end="", file=sys.stderr)
    print("", file=sys.stderr)

    if not episodes or not baseline:
        print("\nNo data — check network access to Yahoo from this machine.")
        return 1

    base_rate = _rate(baseline)
    print(f"\nBASE RATE (every bar, {len(baseline):,} samples): "
          f"{base_rate:.1%} of bars see a {args.big_move_atr}-ATR move within {args.horizon} bars")
    print(f"COMPRESSION EPISODES: {len(episodes):,} across {used} symbols")

    by_grade = defaultdict(list)
    by_grade_ttm = defaultdict(list)
    by_grade_dur = defaultdict(list)
    for e in episodes:
        by_grade[e["grade"]].append(e)
        by_grade_ttm[(e["grade"], e["ttm"])].append(e)
        by_grade_dur[(e["grade"], e["ttm"], e["bucket"])].append(e)

    results = {
        "config": vars(args) | {"period": period, "symbols": len(symbols), "usable": used},
        "base_rate": round(base_rate, 4),
        "episodes": len(episodes),
        "by_grade": _table("BY GRADE (bandwidth percentile at release)", by_grade,
                           base_rate, args.min_sample),
        "by_grade_keltner": _table("BY GRADE × BB-INSIDE-KELTNER", by_grade_ttm, base_rate,
                                   args.min_sample,
                                   lambda k: f"{k[0]:<9} keltner={'yes' if k[1] else 'no'}"),
        "by_grade_keltner_duration": _table(
            "BY GRADE × KELTNER × DURATION (bars coiled)", by_grade_dur, base_rate,
            args.min_sample,
            lambda k: f"{k[0]:<9} keltner={'yes' if k[1] else 'no':<4} {k[2]:>6} bars"),
    }

    # Does the basis actually call the direction, or is it noise?
    print("\nBASIS (MIDDLE-BAND) BIAS vs REALISED DIRECTION")
    print(f"  {'bias at release':<20}{'n':>8}{'went up':>10}{'called it':>12}")
    print("  " + "-" * 50)
    basis = {}
    for bias in ("bullish", "neutral", "bearish"):
        rows = [e for e in episodes if e["mid_bias"] == bias]
        if len(rows) < args.min_sample:
            continue
        ups = sum(r["direction"] == "up" for r in rows)
        called = ups if bias == "bullish" else (len(rows) - ups) if bias == "bearish" else None
        basis[bias] = {"n": len(rows), "up_pct": round(ups / len(rows) * 100, 1),
                       "called_pct": round(called / len(rows) * 100, 1) if called is not None else None}
        print(f"  {bias:<20}{len(rows):>8}{ups / len(rows) * 100:>9.1f}%"
              + (f"{called / len(rows) * 100:>11.1f}%" if called is not None else f"{'—':>12}"))
    results["basis_bias"] = basis

    best = max((r for r in results["by_grade_keltner_duration"] if r["n"] >= args.min_sample),
               key=lambda r: r["lift"] or 0, default=None)
    if best:
        print(f"\nSTRONGEST BUCKET: {best['bucket']}")
        print(f"  {best['big_move_rate']:.1%} big-move rate vs {base_rate:.1%} base "
              f"= {best['lift']}x lift, n={best['n']}")
        print("  -> set config technical.compression to match this bucket "
              "(extreme_pctile / tight_pctile, min_squeeze_bars, require_keltner)")
    results["strongest"] = best

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(results, fh, indent=2, default=str)
        print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
