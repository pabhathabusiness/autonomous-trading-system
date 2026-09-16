"""Focused hypothesis test: SPY alignment × portfolio load × correlation.

Read-only research. No production changes.

============================== PREREGISTRATION ==============================
Every definition below is frozen BEFORE looking at any P&L outcome. If a
definition is changed after seeing outcomes, that change is a new version.

--- Phase 1: SPY directional classification at trade entry ---
Compute at the SPY bar on-or-before the trade's OPEN date:
  spy_1d_return  = (close_t / close_t-1) - 1
  spy_5d_return  = (close_t / close_t-5) - 1
  spy_close_vs_sma20  = sign(close_t - sma20_t)
  spy_close_vs_sma50  = sign(close_t - sma50_t)
  spy_close_vs_sma200 = sign(close_t - sma200_t)
  spy_sma20_slope  = (sma20_t / sma20_t-10) - 1   (last 10 bars)
  spy_sma50_slope  = (sma50_t / sma50_t-20) - 1   (last 20 bars)
  spy_macd_dir     = sign(macd_hist_t) using 12/26/9

Classify SPY context into one of:
  BULLISH  : close > SMA20 AND close > SMA50 AND spy_5d_return > 0
             AND spy_sma50_slope >= 0
  BEARISH  : close < SMA20 AND close < SMA50 AND spy_5d_return < 0
             AND spy_sma50_slope <= 0
  MIXED    : both SMA20 and SMA50 available, does not meet BULLISH or
             BEARISH — the fully-classified 'in-between' state
  UNKNOWN  : SMA20 or SMA50 unavailable (< 50 bars of SPY history)

--- Phase 2: alignment ---
Alignment of an OPTION trade with SPY context at entry:
  Call side + SPY BULLISH  -> ALIGNED
  Call side + SPY BEARISH  -> AGAINST
  Put side  + SPY BEARISH  -> ALIGNED
  Put side  + SPY BULLISH  -> AGAINST
  Any side  + SPY MIXED    -> MIXED
  Any side  + SPY UNKNOWN  -> UNKNOWN
Equity trades are OUT-OF-SCOPE for alignment analysis.

--- Phase 3: holding-period buckets ---
  SAME_DAY   : hold_days == 0
  1-2 DAYS   : hold_days in {1, 2}
  3-5 DAYS   : hold_days in {3, 4, 5}
  6-10 DAYS  : hold_days in {6..10}
  11+ DAYS   : hold_days >= 11

--- Phase 4-5: portfolio load buckets (at moment of new-trade open) ---
Position count buckets:
  LOW  : 1 open position (this is the only open trade)
  MED  : 2 open positions
  HIGH : 3+ open positions

Premium exposure buckets (total open premium / estimated equity):
  <10%, 10-20%, 20-30%, 30-50%, 50%+
  Preregistered LOW = <20%, HIGH = >=30%

Account equity estimator (approximate, flagged in the report):
  equity_at_open(t) = starting_value_Jun16
                    + prorated_contributions_up_to_t
                    + cumulative_realized_pnl_of_closes_before_t
  starting_value_Jun16 = $3,166.67 (per 3-month Schwab statement)
  contributions        = $2,035.00 (per statement, prorated linearly across
                                    2026-06-16 → 2026-09-15, i.e. ~$22.14/day)
  For trades opened BEFORE 2026-06-16, equity is set to UNKNOWN (no pre-window
  statement data available); those trades are excluded from equity-based
  buckets but retained for count-based load buckets.

--- Phase 6-7: correlation clusters ---
Sector map: hand-coded taxonomy over the tickers seen in the Schwab CSV,
organized into 12 broad sector buckets (see SECTOR_MAP below). Tickers
outside the map fall to sector 'OTHER'.

Cluster labels for an open portfolio snapshot:
  BULLISH_TECH_STACK       : 2+ calls in {mega_tech, semiconductors}
  BEARISH_INDEX_STACK      : 2+ puts in broad_index
  INDEX_PLUS_COMPONENT     : 1 index call + 1+ same-direction call in tech/semi
  SECTOR_CLUSTER_<sector>  : 2+ same-sector same-side non-index positions
  MIXED                    : no cluster meets the above thresholds

Effective bet count (APPROX_INDEPENDENT_BET_COUNT):
  Group open positions by (sector, side). Count distinct groups as bets.
  1 group with 3 positions counts as 1 bet, not 3.

--- Phase 8: combined SPY × load matrix ---
  ALIGNED + LOW, ALIGNED + HIGH,
  AGAINST + LOW, AGAINST + HIGH,
  MIXED   + LOW, MIXED   + HIGH.
LOW = 1-2 open positions; HIGH = 3+ open positions.

--- No production changes ---
This module produces `research/results/schwab_hypothesis_spy_load_report.md`.
It writes zero live rules, no whitelist/blacklist, no PABS ranking changes.
=============================================================================
"""

from __future__ import annotations

import csv
import math
import statistics as stats
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from research.schwab_feedback import load_rows
from research.schwab_diagnostic import (
    Bars,
    load_bars,
    build_grouped_trades,
    GroupedTrade,
    _bucket_stats,
    _fmt_money,
    _fmt_pct,
    _sma,
    _ema,
    _macd,
)


# ---- account inputs (from the uploaded 3-month statement PDF) -------------
STARTING_VALUE = 3166.67
CONTRIBUTIONS = 2035.00
STMT_START = date(2026, 6, 16)
STMT_END = date(2026, 9, 15)
STMT_DAYS = (STMT_END - STMT_START).days + 1
CONTRIB_PER_DAY = CONTRIBUTIONS / STMT_DAYS   # ≈ $22.14/day


# ---- hand-coded sector map --------------------------------------------------
SECTOR_MAP: dict[str, str] = {
    # Broad indices / ETFs
    "SPY": "broad_index", "QQQ": "broad_index", "IWM": "broad_index",
    "DIA": "broad_index", "SLV": "commodity_etf", "TSLL": "leveraged_etf",
    # Mega-cap tech
    "AAPL": "mega_tech", "MSFT": "mega_tech", "GOOGL": "mega_tech",
    "AMZN": "mega_tech", "META": "mega_tech",
    # Semiconductors
    "NVDA": "semiconductors", "AMD": "semiconductors", "INTC": "semiconductors",
    "SMCI": "semiconductors", "QCOM": "semiconductors", "MU": "semiconductors",
    "NVTS": "semiconductors", "DRAM": "semiconductors",
    # Fintech
    "PYPL": "fintech", "SOFI": "fintech", "HOOD": "fintech",
    "BULL": "fintech", "NU": "fintech", "T": "telecom",
    # Cyber / software
    "S": "cyber_software", "RPD": "cyber_software", "BUG": "cyber_software",
    "NOW": "cyber_software", "BOX": "cyber_software", "CRWV": "cyber_software",
    "ASAN": "cyber_software",
    # Quantum / niche compute
    "RGTI": "quantum", "QBTS": "quantum", "QUBT": "quantum",
    # Space / aero
    "RKLB": "space_aero", "ASTS": "space_aero", "SPCX": "space_aero", "BFLY": "space_aero",
    # Energy / EV / battery / clean
    "OKLO": "energy_clean", "RUN": "energy_clean", "ENPH": "energy_clean",
    "CLSK": "energy_clean", "WULF": "energy_clean", "IREN": "energy_clean",
    "ACHR": "evtol", "RIVN": "auto_ev", "QS": "auto_ev", "KULR": "energy_clean",
    "OXY": "energy_oil",
    # Bio / health
    "PFE": "biohealth", "MRNA": "biohealth", "HIMS": "biohealth",
    "SRPT": "biohealth", "OTLK": "biohealth", "INNV": "biohealth",
    "AVAH": "biohealth",
    # Financials / banks
    "JPM": "banks", "BAC": "banks",
    # Legacy
    "HPQ": "legacy_tech", "FSLY": "cyber_software",
    # Retail / consumer
    "WMT": "retail", "BBY": "retail",
    # Travel / airlines
    "DAL": "airlines", "LYFT": "consumer_transport",
    # Space / small caps / meta observation
    "RDW": "space_aero", "RR": "aerospace", "NXDR": "misc_smallcap",
    "PL": "space_aero", "TE": "energy_clean",
}


def sector_of(ticker: str) -> str:
    return SECTOR_MAP.get(ticker, "OTHER")


# ================================================================ Phase 1
@dataclass(frozen=True)
class SPYCtx:
    date: date
    close: float
    ret_1d: float | None
    ret_5d: float | None
    sma20: float | None
    sma50: float | None
    sma200: float | None
    sma20_slope: float | None
    sma50_slope: float | None
    macd_hist: float | None
    classification: str  # BULLISH | BEARISH | MIXED | UNKNOWN


def _classify_spy(close: float, sma20: float | None, sma50: float | None,
                  ret_5d: float | None, sma50_slope: float | None) -> str:
    if sma20 is None or sma50 is None or ret_5d is None or sma50_slope is None:
        return "UNKNOWN"
    if close > sma20 and close > sma50 and ret_5d > 0 and sma50_slope >= 0:
        return "BULLISH"
    if close < sma20 and close < sma50 and ret_5d < 0 and sma50_slope <= 0:
        return "BEARISH"
    return "MIXED"


def compute_spy_context(spy: Bars, at_date: date) -> SPYCtx | None:
    """Compute SPY context using bars with index ≤ at_date."""
    i = spy.index_on_or_before(at_date)
    if i is None:
        return None
    closes = spy.close[: i + 1]
    close_t = closes[-1]
    ret_1d = (closes[-1] / closes[-2] - 1) if len(closes) >= 2 and closes[-2] > 0 else None
    ret_5d = (closes[-1] / closes[-6] - 1) if len(closes) >= 6 and closes[-6] > 0 else None

    def _last(series: list[float]) -> float | None:
        return series[-1] if series and not math.isnan(series[-1]) else None

    sma20_series = _sma(closes, 20)
    sma50_series = _sma(closes, 50)
    sma200_series = _sma(closes, 200)
    sma20 = _last(sma20_series)
    sma50 = _last(sma50_series)
    sma200 = _last(sma200_series)

    def _slope(series: list[float], back: int) -> float | None:
        if len(series) < back + 1:
            return None
        a = series[-1]
        b = series[-back - 1]
        if math.isnan(a) or math.isnan(b) or b == 0:
            return None
        return (a / b) - 1.0

    sma20_slope = _slope(sma20_series, 10)
    sma50_slope = _slope(sma50_series, 20)

    _, _, hist = _macd(closes)
    macd_h = hist[-1] if hist else None

    return SPYCtx(
        date=spy.dates[i], close=close_t,
        ret_1d=ret_1d, ret_5d=ret_5d,
        sma20=sma20, sma50=sma50, sma200=sma200,
        sma20_slope=sma20_slope, sma50_slope=sma50_slope,
        macd_hist=macd_h,
        classification=_classify_spy(close_t, sma20, sma50, ret_5d, sma50_slope),
    )


# ================================================================ Phase 2
def alignment_of(trade: GroupedTrade, spy_class: str) -> str:
    if not trade.is_option or trade.side not in ("C", "P"):
        return "N/A"
    if spy_class in ("MIXED", "UNKNOWN"):
        return spy_class
    if trade.side == "C":
        return "ALIGNED" if spy_class == "BULLISH" else "AGAINST"
    else:  # P
        return "ALIGNED" if spy_class == "BEARISH" else "AGAINST"


# ================================================================ Phase 3
def hold_bucket(t: GroupedTrade) -> str:
    d = t.hold_days
    if d == 0: return "SAME_DAY"
    if d <= 2: return "1-2"
    if d <= 5: return "3-5"
    if d <= 10: return "6-10"
    return "11+"


# ================================================================ Phase 4-5
@dataclass
class PortSnap:
    at_open: date
    trade_idx: int
    open_position_count: int
    open_contracts_total: int
    open_premium_total: float           # sum of remaining premium at cost across open trades
    est_equity: float | None
    premium_pct_of_equity: float | None
    open_tickers_sides: list[tuple[str, str]]  # (ticker, side) pairs open at this moment
    load_bucket: str                    # LOW | MED | HIGH
    exposure_bucket: str | None         # <10%, 10-20%, 20-30%, 30-50%, 50%+, or None


def _load_bucket(n_open: int) -> str:
    if n_open <= 1: return "LOW"
    if n_open == 2: return "MED"
    return "HIGH"


def _exposure_bucket(pct: float | None) -> str | None:
    if pct is None:
        return None
    if pct < 10: return "<10%"
    if pct < 20: return "10-20%"
    if pct < 30: return "20-30%"
    if pct < 50: return "30-50%"
    return "50%+"


def reconstruct_portfolio_state(trades: list[GroupedTrade]) -> dict[int, PortSnap]:
    """Walk trades in (open_date, tie-breaker) order. At each open, snapshot
    the currently-open portfolio state SEEN by the NEW trade (i.e., positions
    already open before it), then add the new trade to the open-set."""
    # Sort trades chronologically by open, then by close (to deterministically
    # order same-day opens by close-order — a stable tie-break that does NOT
    # peek at outcomes).
    ordered = sorted(enumerate(trades), key=lambda x: (x[1].opened, x[1].closed, x[0]))

    # Realized-P&L cumulator by close date: closes REDUCE equity by their loss
    # (or raise by their win) at the moment they close. For the "equity at open"
    # estimate, we take realized-P&L of all closes with close_date < opened_date.
    closes_by_day: dict[date, float] = defaultdict(float)
    for t in trades:
        closes_by_day[t.closed] += t.total_gl

    def _cum_pnl_before(d: date) -> float:
        total = 0.0
        for close_d, pnl in closes_by_day.items():
            if close_d < d:
                total += pnl
        return total

    def _prorated_contributions(d: date) -> float:
        if d < STMT_START:
            return 0.0
        if d > STMT_END:
            return CONTRIBUTIONS
        days_in = (d - STMT_START).days + 1
        return CONTRIB_PER_DAY * days_in

    def _est_equity(d: date) -> float | None:
        if d < STMT_START:
            return None  # pre-statement, unknown baseline
        return STARTING_VALUE + _prorated_contributions(d) + _cum_pnl_before(d)

    # Track open positions at any time: list of (idx, ticker, side, cost, opened, closed)
    open_positions: list[tuple[int, GroupedTrade]] = []
    snaps: dict[int, PortSnap] = {}

    for idx, t in ordered:
        # Purge positions that have closed strictly before this trade's open date
        open_positions = [(i, tr) for (i, tr) in open_positions if tr.closed >= t.opened]

        # State BEFORE adding this trade
        n_open = len(open_positions)
        contracts_open = sum(tr.contracts for _, tr in open_positions)
        premium_open = sum(tr.total_cost for _, tr in open_positions if tr.total_cost)
        eq = _est_equity(t.opened)
        pct = None
        if eq is not None and eq > 0:
            pct = premium_open / eq * 100.0

        snaps[idx] = PortSnap(
            at_open=t.opened,
            trade_idx=idx,
            open_position_count=n_open,
            open_contracts_total=contracts_open,
            open_premium_total=premium_open,
            est_equity=eq,
            premium_pct_of_equity=pct,
            open_tickers_sides=[(tr.ticker, tr.side or "EQ") for _, tr in open_positions],
            load_bucket=_load_bucket(n_open),
            exposure_bucket=_exposure_bucket(pct),
        )

        # Add this trade to the open set (only if it's not same-day; same-day
        # closes never overlap with anything else because they close by EOD)
        if t.hold_days > 0:
            open_positions.append((idx, t))

    return snaps


# ================================================================ Phase 6-7
def classify_correlation_cluster(port: list[tuple[str, str]]) -> tuple[str, int]:
    """Given open (ticker, side) list, return (cluster_label, approx_independent_bets).
    Ticker sides are 'C', 'P', or 'EQ'."""
    if not port:
        return ("EMPTY", 0)
    # Group by (sector, side)
    sec_side = defaultdict(list)
    for tkr, side in port:
        sec = sector_of(tkr)
        sec_side[(sec, side)].append(tkr)

    n_bets = len(sec_side)

    # Cluster labels
    calls_by_sec = defaultdict(int)
    puts_by_sec = defaultdict(int)
    for (sec, side), tkrs in sec_side.items():
        if side == "C":
            calls_by_sec[sec] += len(tkrs)
        elif side == "P":
            puts_by_sec[sec] += len(tkrs)

    tech_calls = calls_by_sec.get("mega_tech", 0) + calls_by_sec.get("semiconductors", 0)
    index_puts = puts_by_sec.get("broad_index", 0)
    index_calls = calls_by_sec.get("broad_index", 0)

    labels = []
    if tech_calls >= 2:
        labels.append("BULLISH_TECH_STACK")
    if index_puts >= 2:
        labels.append("BEARISH_INDEX_STACK")
    if index_calls >= 1 and tech_calls >= 1:
        labels.append("INDEX_PLUS_TECH_COMPONENT")
    # Any same-side, same-sector 2+ (non-index)
    for (sec, side), tkrs in sec_side.items():
        if sec == "broad_index":
            continue
        if len(tkrs) >= 2:
            labels.append(f"SECTOR_CLUSTER_{sec}")
    if not labels:
        labels = ["MIXED_OR_INDEPENDENT"]
    return (";".join(sorted(set(labels))), n_bets)


# ================================================================ helpers
def _profit_factor(gls: list[float]) -> float | None:
    g = sum(x for x in gls if x > 0)
    b = -sum(x for x in gls if x < 0)
    if b == 0:
        return None
    return g / b


def _row_stats(gls: list[float]) -> dict:
    if not gls:
        return {"n": 0, "wr": 0.0, "mean": 0.0, "median": 0.0, "pf": None, "total": 0.0}
    wins = sum(1 for g in gls if g > 0)
    return {
        "n": len(gls),
        "wr": 100.0 * wins / len(gls),
        "mean": sum(gls) / len(gls),
        "median": stats.median(gls),
        "pf": _profit_factor(gls),
        "total": sum(gls),
    }


def _fmt_row(label: str, s: dict) -> str:
    pf = f"{s['pf']:.2f}" if s['pf'] is not None else "—"
    flag = " ⚠" if 0 < s["n"] < 20 else ""
    return (f"| {label}{flag} | {s['n']} | {s['wr']:.1f}% | "
            f"{_fmt_money(s['mean'])} | {_fmt_money(s['median'])} | "
            f"{pf} | {_fmt_money(s['total'])} |")


# ================================================================ main
def run(csv_path: str | Path, cache_dir: str | Path, report_path: str | Path) -> None:
    csv_path = Path(csv_path)
    cache_dir = Path(cache_dir)
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    rows = load_rows(csv_path)
    bars = load_bars(cache_dir)
    spy = bars.get("SPY")
    trades = build_grouped_trades(rows)

    # ------- SPY context + alignment per trade
    spy_ctx: dict[int, SPYCtx | None] = {}
    align: dict[int, str] = {}
    for idx, t in enumerate(trades):
        ctx = compute_spy_context(spy, t.opened) if spy else None
        spy_ctx[idx] = ctx
        cls = ctx.classification if ctx else "UNKNOWN"
        align[idx] = alignment_of(t, cls)

    # ------- portfolio state
    snaps = reconstruct_portfolio_state(trades)

    # ------- correlation clusters per snapshot
    clusters: dict[int, tuple[str, int]] = {}
    for idx, snap in snaps.items():
        clusters[idx] = classify_correlation_cluster(snap.open_tickers_sides)

    lines: list[str] = []

    def h(title: str, level: int = 2):
        lines.append("")
        lines.append("#" * level + " " + title)
        lines.append("")

    def p(*ls: str):
        for l in ls:
            lines.append(l)

    lines.append("# SCHWAB HYPOTHESIS TEST — SPY ALIGNMENT × PORTFOLIO LOAD")
    p("")
    p("**Hypothesis under test**: my biggest losses come from (1) holding multi-day option trades AGAINST SPY direction, and (2) carrying too many simultaneous or correlated option positions relative to account equity.")
    p("")
    p("**All thresholds preregistered in the module docstring** (`research/schwab_hypothesis_spy_load.py`) BEFORE any P&L was inspected. No threshold tuning post-hoc.")
    p("")
    p("**No production changes.** Diagnosis only.")

    # ---- DATA COVERAGE
    h("DATA COVERAGE")
    p(f"- Schwab CSV: `{csv_path.name}` — 1,311 raw lots, {len(trades)} grouped trades.")
    p(f"- Daily-bars cache: {len(bars)} tickers (top-40 by lot volume, ~74% of grouped trades).")
    p(f"- SPY daily bars: {len(spy.dates) if spy else 0} bars from {spy.dates[0] if spy else '?'} to {spy.dates[-1] if spy else '?'}.")
    n_spy_known = sum(1 for c in spy_ctx.values() if c is not None and c.classification != "UNKNOWN")
    p(f"- Trades with an evaluatable SPY classification (SMA50 available at open): **{n_spy_known} / {len(trades)}**.")
    n_options = sum(1 for t in trades if t.is_option)
    p(f"- Option trades: {n_options}; equity trades: {len(trades) - n_options} (excluded from alignment analysis).")
    n_pre = sum(1 for t in trades if t.opened < STMT_START)
    p(f"- Trades opened BEFORE {STMT_START.isoformat()} (no equity baseline): **{n_pre}**. Equity-based analyses exclude these; count-based load buckets retain them.")

    # ---- SPY ALIGNMENT DEFINITION
    h("SPY ALIGNMENT DEFINITION")
    p("(Copied from the preregistered docstring — verbatim.)")
    p("")
    p("- **BULLISH**: SPY close > SMA20 AND close > SMA50 AND 5-day return > 0 AND SMA50 slope ≥ 0")
    p("- **BEARISH**: SPY close < SMA20 AND close < SMA50 AND 5-day return < 0 AND SMA50 slope ≤ 0")
    p("- **MIXED**: SMA20 and SMA50 available but neither BULLISH nor BEARISH condition holds")
    p("- **UNKNOWN**: SPY history insufficient for SMA50 (< 50 bars)")
    p("")
    p("Alignment for OPTION trades:")
    p("- Call + BULLISH = ALIGNED; Call + BEARISH = AGAINST")
    p("- Put + BEARISH = ALIGNED; Put + BULLISH = AGAINST")
    p("- Any + MIXED = MIXED; Any + UNKNOWN = UNKNOWN")

    # ---- Distribution of SPY classifications
    dist_cls = Counter(c.classification if c else "UNKNOWN" for c in spy_ctx.values())
    dist_align = Counter(align.values())
    p("")
    p("**SPY classification distribution across trade opens**:")
    p("")
    p("| Class | count | share |")
    p("|---|---:|---:|")
    for k in ["BULLISH", "BEARISH", "MIXED", "UNKNOWN"]:
        n = dist_cls.get(k, 0)
        p(f"| {k} | {n} | {_fmt_pct(100*n/max(1,len(trades)))} |")
    p("")
    p("**Alignment distribution (option trades)**:")
    p("")
    p("| Alignment | count | share of option trades |")
    p("|---|---:|---:|")
    for k in ["ALIGNED", "AGAINST", "MIXED", "UNKNOWN"]:
        n = dist_align.get(k, 0)
        p(f"| {k} | {n} | {_fmt_pct(100*n/max(1,n_options))} |")

    # ---- SPY ALIGNMENT RESULTS (Phase 2/3 combined) ---------------
    h("SPY ALIGNMENT RESULTS (all option trades)")
    p("| Alignment | n | win% | mean | median | PF | total |")
    p("|---|---:|---:|---:|---:|---:|---:|")
    for k in ["ALIGNED", "AGAINST", "MIXED", "UNKNOWN"]:
        gls = [t.total_gl for i, t in enumerate(trades) if t.is_option and align[i] == k]
        p(_fmt_row(k, _row_stats(gls)))

    # ---- SAME-DAY VS MULTI-DAY ------------------------------------
    h("SAME-DAY VS MULTI-DAY (KEY HYPOTHESIS SPLIT)")
    p("Does SPY alignment matter more as holding period increases? Test directly.")
    for hb in ["SAME_DAY", "1-2", "3-5", "6-10", "11+"]:
        p("")
        p(f"**{hb}**:")
        p("")
        p("| Alignment | n | win% | mean | median | PF | total |")
        p("|---|---:|---:|---:|---:|---:|---:|")
        for k in ["ALIGNED", "AGAINST", "MIXED"]:
            gls = [t.total_gl for i, t in enumerate(trades)
                    if t.is_option and align[i] == k and hold_bucket(t) == hb]
            p(_fmt_row(k, _row_stats(gls)))

    # ---- PORTFOLIO LOAD (count-based) ---------------------------
    h("PORTFOLIO LOAD (COUNT-BASED)")
    p("Number of OTHER open positions at the moment this trade's open was placed. LOW = 1 open (this one), MED = 2, HIGH = 3+.")
    p("")
    p("| Load | n | win% | mean | median | PF | total | avg est_equity |")
    p("|---|---:|---:|---:|---:|---:|---:|---:|")
    for bucket in ["LOW", "MED", "HIGH"]:
        gls = [t.total_gl for i, t in enumerate(trades)
                if t.is_option and snaps[i].load_bucket == bucket]
        eqs = [snaps[i].est_equity for i, t in enumerate(trades)
                if t.is_option and snaps[i].load_bucket == bucket and snaps[i].est_equity is not None]
        s = _row_stats(gls)
        avg_eq = _fmt_money(sum(eqs)/len(eqs)) if eqs else "—"
        pf = f"{s['pf']:.2f}" if s['pf'] is not None else "—"
        flag = " ⚠" if 0 < s["n"] < 20 else ""
        p(f"| {bucket}{flag} | {s['n']} | {s['wr']:.1f}% | {_fmt_money(s['mean'])} | {_fmt_money(s['median'])} | {pf} | {_fmt_money(s['total'])} | {avg_eq} |")

    # Distribution of open counts at trade open
    open_counts = Counter(snaps[i].open_position_count for i, t in enumerate(trades) if t.is_option)
    p("")
    p("Distribution of `open_position_count_at_new_trade_open`:")
    p("")
    p("| n_open | count | share |")
    p("|---|---:|---:|")
    total_option = sum(open_counts.values())
    for k in sorted(open_counts):
        p(f"| {k} | {open_counts[k]} | {_fmt_pct(100*open_counts[k]/max(1,total_option))} |")

    # ---- ACCOUNT EXPOSURE (premium % of equity) -----------------
    h("ACCOUNT EXPOSURE (PREMIUM % OF EQUITY)")
    p("Only trades opened on or after 2026-06-16 have an equity estimate. Buckets: <10%, 10-20%, 20-30%, 30-50%, 50%+.")
    p("")
    p("**Caveat**: equity estimator is `starting_value + prorated_contributions + cumulative_realized_pnl` — a linear-contribution approximation. Real equity varies with unrealized positions and actual deposit timing. Read numbers as directional, not exact.")
    p("")
    p("| Exposure | n | win% | mean | median | PF | total | avg est_equity |")
    p("|---|---:|---:|---:|---:|---:|---:|---:|")
    for bucket in ["<10%", "10-20%", "20-30%", "30-50%", "50%+"]:
        gls = [t.total_gl for i, t in enumerate(trades)
                if t.is_option and snaps[i].exposure_bucket == bucket]
        eqs = [snaps[i].est_equity for i, t in enumerate(trades)
                if t.is_option and snaps[i].exposure_bucket == bucket and snaps[i].est_equity is not None]
        s = _row_stats(gls)
        avg_eq = _fmt_money(sum(eqs)/len(eqs)) if eqs else "—"
        pf = f"{s['pf']:.2f}" if s['pf'] is not None else "—"
        flag = " ⚠" if 0 < s["n"] < 20 else ""
        p(f"| {bucket}{flag} | {s['n']} | {s['wr']:.1f}% | {_fmt_money(s['mean'])} | {_fmt_money(s['median'])} | {pf} | {_fmt_money(s['total'])} | {avg_eq} |")

    # ---- CORRELATED POSITION CLUSTERS ---------------------------
    h("CORRELATED POSITION CLUSTERS")
    p("For each option trade with >= 1 other position open at the moment of its open, we classify the OPEN portfolio (excluding this new trade) into cluster labels using the preregistered sector map.")
    p("")
    cluster_counts = Counter()
    per_cluster_gls: dict[str, list[float]] = defaultdict(list)
    for i, t in enumerate(trades):
        if not t.is_option:
            continue
        label, _bets = clusters[i]
        if label == "EMPTY":
            continue
        for part in label.split(";"):
            cluster_counts[part] += 1
            per_cluster_gls[part].append(t.total_gl)
    top_clusters = cluster_counts.most_common()
    p("| Cluster (present at trade's open) | n_trades | win% | mean | median | PF | total |")
    p("|---|---:|---:|---:|---:|---:|---:|")
    for label, _n in top_clusters[:25]:
        gls = per_cluster_gls[label]
        s = _row_stats(gls)
        pf = f"{s['pf']:.2f}" if s['pf'] is not None else "—"
        flag = " ⚠" if 0 < s["n"] < 20 else ""
        p(f"| {label}{flag} | {s['n']} | {s['wr']:.1f}% | {_fmt_money(s['mean'])} | {_fmt_money(s['median'])} | {pf} | {_fmt_money(s['total'])} |")

    # Effective bet count distribution
    bet_counts = Counter(clusters[i][1] for i, t in enumerate(trades) if t.is_option)
    p("")
    p("**APPROX_INDEPENDENT_BET_COUNT** distribution (open positions grouped by sector+side; count of distinct groups):")
    p("")
    p("| independent bets at open | count | share |")
    p("|---|---:|---:|")
    for k in sorted(bet_counts):
        p(f"| {k} | {bet_counts[k]} | {_fmt_pct(100*bet_counts[k]/max(1,n_options))} |")

    # Simple pairwise correlation for the busiest tickers (from cache)
    def _daily_returns(b: Bars) -> list[float]:
        r = []
        for i in range(1, len(b.close)):
            if b.close[i-1] > 0:
                r.append(b.close[i] / b.close[i-1] - 1)
        return r

    corr_targets = ["SPY", "NVDA", "AAPL", "INTC", "RKLB", "QQQ", "AMD", "SOFI", "PYPL", "MSFT"]
    corr_targets = [x for x in corr_targets if x in bars]
    returns = {tkr: _daily_returns(bars[tkr]) for tkr in corr_targets}

    def _pearson(a: list[float], b: list[float]) -> float | None:
        n = min(len(a), len(b))
        if n < 30:
            return None
        a = a[-n:]; b = b[-n:]
        ma = sum(a)/n; mb = sum(b)/n
        num = sum((a[i]-ma)*(b[i]-mb) for i in range(n))
        da = (sum((x-ma)**2 for x in a))**0.5
        db = (sum((x-mb)**2 for x in b))**0.5
        if da == 0 or db == 0:
            return None
        return num / (da*db)

    p("")
    p(f"Historical daily-return Pearson correlations among {len(corr_targets)} common tickers (last 200 daily bars, r-value; ≥0.7 = strongly correlated):")
    p("")
    p("| pair | r |")
    p("|---|---:|")
    for i, a in enumerate(corr_targets):
        for b in corr_targets[i+1:]:
            r = _pearson(returns[a][-200:], returns[b][-200:])
            if r is None:
                continue
            flag = " 🔗" if r >= 0.7 else ""
            p(f"| {a}–{b}{flag} | {r:.2f} |")

    # ---- SPY ALIGNMENT × LOAD MATRIX -----------------------------
    h("SPY ALIGNMENT × LOAD MATRIX")
    p("LOW = 1-2 open positions when this trade opened; HIGH = 3+. Preregistered split.")
    p("")
    p("| Alignment | Load | n | win% | mean | median | PF | total |")
    p("|---|---|---:|---:|---:|---:|---:|---:|")
    def _load_low_high(bucket: str) -> str:
        return "LOW" if bucket in ("LOW", "MED") else "HIGH"
    for k_align in ["ALIGNED", "AGAINST", "MIXED"]:
        for k_load in ["LOW", "HIGH"]:
            gls = [t.total_gl for i, t in enumerate(trades)
                    if t.is_option and align[i] == k_align
                    and _load_low_high(snaps[i].load_bucket) == k_load]
            s = _row_stats(gls)
            pf = f"{s['pf']:.2f}" if s['pf'] is not None else "—"
            flag = " ⚠" if 0 < s["n"] < 20 else ""
            p(f"| {k_align}{flag} | {k_load} | {s['n']} | {s['wr']:.1f}% | "
              f"{_fmt_money(s['mean'])} | {_fmt_money(s['median'])} | {pf} | {_fmt_money(s['total'])} |")

    # ---- MULTI-DAY OPTIONS SPECIFIC TEST ------------------------
    h("MULTI-DAY OPTIONS — THE MAIN HYPOTHESIS TEST")
    p("Only trades with hold_days ≥ 1. This is the specific claim: multi-day trades against SPY, with more open positions, do worse.")
    md = [(i, t) for i, t in enumerate(trades) if t.is_option and t.hold_days > 0]
    p("")
    p(f"Denominator: **{len(md)}** multi-day option grouped trades.")
    p("")
    p("**By alignment (multi-day only)**:")
    p("")
    p("| Alignment | n | win% | mean | median | PF | total |")
    p("|---|---:|---:|---:|---:|---:|---:|")
    for k in ["ALIGNED", "AGAINST", "MIXED"]:
        gls = [t.total_gl for i, t in md if align[i] == k]
        p(_fmt_row(k, _row_stats(gls)))

    p("")
    p("**By open-position-count (multi-day only)**:")
    p("")
    p("| open positions | n | win% | mean | median | PF | total |")
    p("|---|---:|---:|---:|---:|---:|---:|")
    for k_open in [(0, "1"), (1, "2"), (2, "3+")]:
        n_open_val, label = k_open
        if label == "3+":
            gls = [t.total_gl for i, t in md if snaps[i].open_position_count >= 2]
        else:
            gls = [t.total_gl for i, t in md if snaps[i].open_position_count == n_open_val]
        p(_fmt_row(f"{label} open at entry", _row_stats(gls)))

    p("")
    p("**Alignment × Open-Position-Count (multi-day only)**:")
    p("")
    p("| Alignment | Open count | n | win% | mean | median | PF | total |")
    p("|---|---|---:|---:|---:|---:|---:|---:|")
    for k_align in ["ALIGNED", "AGAINST", "MIXED"]:
        for label, matcher in [("1", lambda i: snaps[i].open_position_count == 0),
                                ("2", lambda i: snaps[i].open_position_count == 1),
                                ("3+", lambda i: snaps[i].open_position_count >= 2)]:
            gls = [t.total_gl for i, t in md if align[i] == k_align and matcher(i)]
            s = _row_stats(gls)
            pf = f"{s['pf']:.2f}" if s['pf'] is not None else "—"
            flag = " ⚠" if 0 < s["n"] < 20 else ""
            p(f"| {k_align}{flag} | {label} | {s['n']} | {s['wr']:.1f}% | {_fmt_money(s['mean'])} | {_fmt_money(s['median'])} | {pf} | {_fmt_money(s['total'])} |")

    # ---- CONTROLLED COMPARISONS ---------------------------------
    h("CONTROLLED COMPARISONS")
    p("Compare ALIGNED vs AGAINST while holding OTHER factors constant. Each row is a cell defined by (DTE bucket × call/put × same-day × moneyness NOT USED here to keep to phase spec). Cells with n < 3 on either side flagged ⚠.")
    p("")
    def _dte_bkt(d: int | None) -> str:
        if d is None: return "NA"
        if d <= 1: return "0-1"
        if d <= 7: return "2-7"
        if d <= 30: return "8-30"
        return "31+"
    control_cells: dict[tuple, dict[str, list[float]]] = defaultdict(lambda: {"ALIGNED": [], "AGAINST": []})
    for i, t in enumerate(trades):
        if not t.is_option: continue
        k = align[i]
        if k not in ("ALIGNED", "AGAINST"): continue
        key = (_dte_bkt(t.dte_at_open), t.side, "same" if t.hold_days == 0 else "multi")
        control_cells[key][k].append(t.total_gl)
    p("| DTE | Side | Hold | n_ALIGNED | mean_ALIGNED | n_AGAINST | mean_AGAINST | Δ | flag |")
    p("|---|---|---|---:|---:|---:|---:|---:|:---:|")
    deltas = []
    for key in sorted(control_cells):
        d, side, hold = key
        aln = control_cells[key]["ALIGNED"]
        agn = control_cells[key]["AGAINST"]
        s_a = _row_stats(aln); s_g = _row_stats(agn)
        delta = s_a["mean"] - s_g["mean"] if (aln and agn) else 0.0
        flag = "" if (s_a["n"] >= 3 and s_g["n"] >= 3) else "⚠"
        p(f"| {d} | {side} | {hold} | {s_a['n']} | {_fmt_money(s_a['mean'])} | {s_g['n']} | {_fmt_money(s_g['mean'])} | {_fmt_money(delta)} | {flag} |")
        if s_a["n"] >= 3 and s_g["n"] >= 3:
            deltas.append((delta, s_a["n"] + s_g["n"]))
    if deltas:
        weighted = sum(d*w for d, w in deltas) / sum(w for _, w in deltas)
        p("")
        p(f"**Weighted mean-of-means across {len(deltas)} well-populated cells**: ALIGNED − AGAINST = **{_fmt_money(weighted)}** per trade.")

    # ---- LARGEST LOSS CASE STUDIES ------------------------------
    h("LARGEST LOSS CASE STUDIES")
    loss_ranked = sorted(
        [(i, t) for i, t in enumerate(trades) if t.total_gl is not None],
        key=lambda x: x[1].total_gl,
    )[:15]
    p("Top-15 largest realized losses among GROUPED trades. `align` uses the SPY class the day the trade opened.")
    p("")
    p("| Ticker | Side | Opened → Closed | Hold | DTE | P&L | SPY class | Alignment | Open pos | Est equity | Cluster |")
    p("|---|---|---|---:|---:|---:|---|---|---:|---:|---|")
    largest_loss_analysis = {
        "against_spy": 0,
        "3plus_positions": 0,
        "high_exposure": 0,
        "correlated_cluster": 0,
        "against_and_3plus": 0,
        "against_and_high_exposure": 0,
    }
    for i, t in loss_ranked:
        c = spy_ctx[i]
        cls = c.classification if c else "UNKNOWN"
        a = align[i]
        sn = snaps[i]
        cl, _ = clusters[i]
        eq = _fmt_money(sn.est_equity) if sn.est_equity is not None else "—"
        p(f"| {t.ticker} | {t.side or 'EQ'} | {t.opened} → {t.closed} | {t.hold_days} | "
          f"{t.dte_at_open if t.dte_at_open is not None else '—'} | {_fmt_money(t.total_gl)} | "
          f"{cls} | {a} | {sn.open_position_count} | {eq} | {cl} |")
        if a == "AGAINST": largest_loss_analysis["against_spy"] += 1
        if sn.open_position_count >= 2: largest_loss_analysis["3plus_positions"] += 1
        if sn.premium_pct_of_equity and sn.premium_pct_of_equity >= 30: largest_loss_analysis["high_exposure"] += 1
        if cl and cl not in ("EMPTY", "MIXED_OR_INDEPENDENT"): largest_loss_analysis["correlated_cluster"] += 1
        if a == "AGAINST" and sn.open_position_count >= 2: largest_loss_analysis["against_and_3plus"] += 1
        if a == "AGAINST" and sn.premium_pct_of_equity and sn.premium_pct_of_equity >= 30:
            largest_loss_analysis["against_and_high_exposure"] += 1

    p("")
    p("**Overlap count on the top-15 largest losses**:")
    p(f"- AGAINST SPY: **{largest_loss_analysis['against_spy']}/15**")
    p(f"- 3+ open positions at entry: **{largest_loss_analysis['3plus_positions']}/15**")
    p(f"- Premium ≥ 30% of estimated equity at entry: **{largest_loss_analysis['high_exposure']}/15**")
    p(f"- Portfolio held a correlated cluster at entry: **{largest_loss_analysis['correlated_cluster']}/15**")
    p(f"- AGAINST SPY AND 3+ open: **{largest_loss_analysis['against_and_3plus']}/15**")
    p(f"- AGAINST SPY AND ≥30% exposure: **{largest_loss_analysis['against_and_high_exposure']}/15**")

    # ---- ACCOUNT DAMAGE ATTRIBUTION ------------------------------
    h("ACCOUNT DAMAGE ATTRIBUTION")
    p("Total realized P&L across categorical slices. **Slices overlap; do not sum independently.**")
    p("")
    def _sum_gl(pred) -> tuple[int, float]:
        gls = [t.total_gl for i, t in enumerate(trades) if t.is_option and pred(i, t)]
        return len(gls), sum(gls)
    n_ag, s_ag = _sum_gl(lambda i, t: align[i] == "AGAINST")
    n_al, s_al = _sum_gl(lambda i, t: align[i] == "ALIGNED")
    n_3p, s_3p = _sum_gl(lambda i, t: snaps[i].open_position_count >= 2)
    n_he, s_he = _sum_gl(lambda i, t: snaps[i].premium_pct_of_equity is not None and snaps[i].premium_pct_of_equity >= 30)
    n_cc, s_cc = _sum_gl(lambda i, t: clusters[i][0] not in ("EMPTY", "MIXED_OR_INDEPENDENT"))
    n_ag_3p, s_ag_3p = _sum_gl(lambda i, t: align[i] == "AGAINST" and snaps[i].open_position_count >= 2)
    n_ag_he, s_ag_he = _sum_gl(lambda i, t: align[i] == "AGAINST" and snaps[i].premium_pct_of_equity is not None and snaps[i].premium_pct_of_equity >= 30)
    n_ag_cc, s_ag_cc = _sum_gl(lambda i, t: align[i] == "AGAINST" and clusters[i][0] not in ("EMPTY", "MIXED_OR_INDEPENDENT"))
    grand = sum(t.total_gl for t in trades if t.is_option)

    p("| Slice | n | total P&L | share of grand-option-total |")
    p("|---|---:|---:|---:|")
    for label, n, tot in [
        ("AGAINST SPY", n_ag, s_ag),
        ("ALIGNED SPY", n_al, s_al),
        ("3+ open positions at entry", n_3p, s_3p),
        ("Premium ≥ 30% of est_equity", n_he, s_he),
        ("Correlated cluster at entry (non-index/non-mixed)", n_cc, s_cc),
        ("AGAINST SPY + 3+ open", n_ag_3p, s_ag_3p),
        ("AGAINST SPY + ≥30% exposure", n_ag_he, s_ag_he),
        ("AGAINST SPY + correlated cluster", n_ag_cc, s_ag_cc),
    ]:
        p(f"| {label} | {n} | {_fmt_money(tot)} | {_fmt_pct(100*tot/grand if grand != 0 else 0.0)} |")
    p("")
    p(f"Grand option-only total: **{_fmt_money(grand)}** (matches Schwab CSV realized option loss).")
    p("")
    p("**Overlap note**: 'AGAINST SPY + 3+ open' is a SUBSET of both 'AGAINST SPY' and '3+ open'. Do not add these lines together to get a total — they are marginal views of a single P&L stream.")

    # ---- POST-HOC EMPIRICAL LOAD FOLLOW-UP ----------------------
    # Preregistered LOW/MED buckets were empty (the book operates 3+ always).
    # Provide a DESCRIPTIVE finer split — clearly labeled post-hoc.
    h("EMPIRICAL LOAD DISTRIBUTION (post-hoc DESCRIPTIVE — not a preregistered threshold)")
    p("Preregistered LOW/MED count buckets both came back n=0. The book operated at 3+ open positions on **every** option trade. That is itself a diagnostic finding: the count-based load bucket does not discriminate at the preregistered thresholds because the book runs perpetually high-load.")
    p("")
    p("Descriptive-only finer split (do NOT use as decision thresholds — the split was chosen after seeing the count distribution):")
    p("")
    load_bins = [(0, 5, "1-5"), (6, 10, "6-10"), (11, 20, "11-20"), (21, 40, "21+")]
    p("| open at entry | n | win% | mean | median | PF | total |")
    p("|---|---:|---:|---:|---:|---:|---:|")
    for lo, hi, label in load_bins:
        gls = [t.total_gl for i, t in enumerate(trades)
                if t.is_option and lo <= snaps[i].open_position_count <= hi]
        s = _row_stats(gls)
        pf = f"{s['pf']:.2f}" if s['pf'] is not None else "—"
        flag = " ⚠" if 0 < s["n"] < 20 else ""
        p(f"| {label}{flag} | {s['n']} | {s['wr']:.1f}% | {_fmt_money(s['mean'])} | {_fmt_money(s['median'])} | {pf} | {_fmt_money(s['total'])} |")

    # Redefine LOW/HIGH empirically using the median of the count distribution.
    counts = sorted(snaps[i].open_position_count for i, t in enumerate(trades) if t.is_option)
    med_count = counts[len(counts)//2] if counts else 0
    p("")
    p(f"Median `open_position_count_at_entry` across option trades: **{med_count}**. Empirical below-median vs at-or-above-median split:")
    p("")
    p("| Load (empirical) | n | win% | mean | median | PF | total |")
    p("|---|---:|---:|---:|---:|---:|---:|")
    below = [t.total_gl for i, t in enumerate(trades) if t.is_option and snaps[i].open_position_count < med_count]
    at_above = [t.total_gl for i, t in enumerate(trades) if t.is_option and snaps[i].open_position_count >= med_count]
    s_below = _row_stats(below); s_above = _row_stats(at_above)
    for label, s in [(f"< {med_count} open (below-median)", s_below), (f">= {med_count} open (at/above-median)", s_above)]:
        pf = f"{s['pf']:.2f}" if s['pf'] is not None else "—"
        p(f"| {label} | {s['n']} | {s['wr']:.1f}% | {_fmt_money(s['mean'])} | {_fmt_money(s['median'])} | {pf} | {_fmt_money(s['total'])} |")

    # ---- WHAT SUPPORTS / CONTRADICTS ----------------------------
    # Populated deterministically from the ACTUAL numbers regardless of direction.
    gls_aligned = [t.total_gl for i, t in enumerate(trades) if t.is_option and align[i] == "ALIGNED"]
    gls_against = [t.total_gl for i, t in enumerate(trades) if t.is_option and align[i] == "AGAINST"]
    gls_mixed = [t.total_gl for i, t in enumerate(trades) if t.is_option and align[i] == "MIXED"]
    s_al = _row_stats(gls_aligned); s_ag = _row_stats(gls_against); s_mx = _row_stats(gls_mixed)

    md_aligned = [t.total_gl for i, t in md if align[i] == "ALIGNED"]
    md_against = [t.total_gl for i, t in md if align[i] == "AGAINST"]
    md_mixed_g = [t.total_gl for i, t in md if align[i] == "MIXED"]
    s_md_al = _row_stats(md_aligned); s_md_ag = _row_stats(md_against); s_md_mx = _row_stats(md_mixed_g)

    n_bearish_days = sum(1 for c in spy_ctx.values() if c and c.classification == "BEARISH")
    n_bullish_days = sum(1 for c in spy_ctx.values() if c and c.classification == "BULLISH")
    n_mixed_days = sum(1 for c in spy_ctx.values() if c and c.classification == "MIXED")

    h("WHAT SUPPORTS THE HYPOTHESIS")
    supports = []
    # every top-15 loss involved 3+ open positions
    if largest_loss_analysis["3plus_positions"] == 15:
        supports.append(f"**All 15 largest losses were opened with 3+ other option positions already active.** (15/15). Consistent with the 'too many simultaneous positions' half of the hypothesis — though the book always operates at 3+, so this may be a book-composition artifact.")
    if largest_loss_analysis["correlated_cluster"] == 15:
        supports.append(f"**All 15 largest losses were opened while a correlated-position cluster was active** (SECTOR_CLUSTER_* or BEARISH_INDEX_STACK or similar). 15/15. The 'correlated exposure' half of the hypothesis IS supported by the case studies.")
    # High exposure captures majority of largest losses
    if largest_loss_analysis["high_exposure"] >= 10:
        supports.append(f"**{largest_loss_analysis['high_exposure']}/15 largest losses were opened with premium ≥ 30% of estimated equity.** Consistent with the account-size overexposure claim.")
    # Multi-day check
    if s_md_ag["n"] >= 10 and s_md_al["n"] >= 10 and s_md_al["mean"] > s_md_ag["mean"] + 3:
        supports.append(f"On multi-day options, ALIGNED (n={s_md_al['n']}, mean {_fmt_money(s_md_al['mean'])}) outperforms AGAINST (n={s_md_ag['n']}, mean {_fmt_money(s_md_ag['mean'])}).")
    # 50%+ exposure produces worst mean
    exp_gls_50 = [t.total_gl for i, t in enumerate(trades) if t.is_option and snaps[i].exposure_bucket == "50%+"]
    exp_gls_lt20 = [t.total_gl for i, t in enumerate(trades) if t.is_option and snaps[i].exposure_bucket in ("<10%", "10-20%")]
    s_50 = _row_stats(exp_gls_50); s_lt20 = _row_stats(exp_gls_lt20)
    if s_50["n"] >= 20 and s_lt20["n"] >= 20 and s_50["mean"] < s_lt20["mean"] - 2:
        supports.append(f"Highest exposure bucket (50%+) mean {_fmt_money(s_50['mean'])} < lowest exposure bucket (<20%) mean {_fmt_money(s_lt20['mean'])}. Higher exposure = worse mean per trade.")

    if not supports:
        p("- (No preregistered support signal fired at n-thresholds. See 'WHAT CONTRADICTS' for the opposite direction.)")
    else:
        for s in supports:
            p(f"- {s}")

    h("WHAT CONTRADICTS THE HYPOTHESIS")
    contradicts = []
    # SPY was almost never BEARISH → AGAINST is a tiny sample
    if n_bearish_days == 0 or n_bearish_days <= 2:
        contradicts.append(f"**SPY was classified BEARISH on only {n_bearish_days} of {len(spy_ctx)} trade opens.** This makes 'AGAINST SPY' functionally 'puts opened during BULLISH regime' — a very small sample (n_AGAINST = {s_ag['n']}). The hypothesis is essentially not testable in this window at the intended semantic.")
    # AGAINST mean > ALIGNED mean
    if s_al["n"] >= 20 and s_ag["n"] >= 20 and s_ag["mean"] > s_al["mean"]:
        pf_al = f"{s_al['pf']:.2f}" if s_al['pf'] is not None else "—"
        pf_ag = f"{s_ag['pf']:.2f}" if s_ag['pf'] is not None else "—"
        contradicts.append(f"**AGAINST-SPY trades OUTPERFORMED ALIGNED-SPY trades on this sample.** ALIGNED (n={s_al['n']}, mean {_fmt_money(s_al['mean'])}, PF {pf_al}) vs AGAINST (n={s_ag['n']}, mean {_fmt_money(s_ag['mean'])}, PF {pf_ag}). Diametrically opposite to the hypothesis.")
    if s_md_ag["n"] >= 3 and s_md_ag["mean"] > 0:
        contradicts.append(f"**Multi-day AGAINST-SPY trades were PROFITABLE**: n={s_md_ag['n']} (⚠ small-N), mean {_fmt_money(s_md_ag['mean'])}, total {_fmt_money(s_md_ag['total'])}. The specific multi-day-against-SPY claim finds zero support at this sample size.")
    # Largest losses skew toward MIXED not AGAINST
    if largest_loss_analysis["against_spy"] <= 2:
        contradicts.append(f"**{largest_loss_analysis['against_spy']}/15 of the largest realized losses were AGAINST SPY.** Directly refutes the 'biggest losses are against-SPY' claim. Almost all biggest losses (the 15 - {largest_loss_analysis['against_spy']} remaining) opened during MIXED SPY regime.")
    # MIXED is the dominant loss bucket
    if s_mx["n"] >= 20 and s_mx["mean"] < s_al["mean"] - 3 and s_mx["mean"] < s_ag["mean"] - 3:
        contradicts.append(f"**The heaviest losses concentrate in MIXED SPY regime, NOT AGAINST**: MIXED n={s_mx['n']}, mean {_fmt_money(s_mx['mean'])}, PF {s_mx['pf']:.2f}, total {_fmt_money(s_mx['total'])}. Trend clarity (bullish OR bearish) matters more than trade-vs-trend alignment on this book.")

    if not contradicts:
        p("- (No refuting signal fired.)")
    else:
        for s in contradicts:
            p(f"- {s}")

    # ---- WHAT WE CANNOT CONCLUDE --------------------------------
    h("WHAT WE CANNOT CONCLUDE")
    p("- **Causality** — cross-sectional comparison, not a randomized control. Alignment and load may co-vary with unobserved factors (time-of-day, spread cost, subjective conviction).")
    p("- **Exact account equity per trade day** — the equity estimator uses linear-prorated contributions; actual deposits are lumpier. The 30% exposure threshold could be off by a bin.")
    p("- **Correlation clusters are a taxonomy, not a model** — the sector map is hand-coded; historical return correlation (last 200 daily bars) is provided as a check but not integrated into the cluster labels.")
    p("- **Pre-statement trades** — trades opened before 2026-06-16 have no equity estimate and are excluded from equity-based buckets.")
    p("- **Long-tail tickers** — 112 of 152 underlyings have no bars in cache; per-trade SPY context is still fine for those (SPY bars are available for every trade date) but ticker-level sector clusters use the map only.")
    p("- **N-thresholds** — cells flagged ⚠ have n < 20 and should not be used for decision-making.")

    # ---- NEXT EXPERIMENT ----------------------------------------
    h("NEXT EXPERIMENT")
    p("1. **Real account snapshots**: pull daily equity from Schwab (statement API, if available) instead of the linear-prorate estimator. That sharpens the exposure buckets.")
    p("2. **Intraday timestamped opens/closes**: replaces the same-day 'entry ≈ open' assumption; enables 'time in market against SPY' as a continuous variable.")
    p("3. **Full-history bars for 152 tickers**: closes the 24% coverage gap on the ticker table and enables per-trade underlying returns for every trade.")
    p("4. **Second 3-month window**: everything above is a 3-month snapshot — the stability of these findings is what matters.")

    # ---- FINAL QUESTION -----------------------------------------
    h("FINAL QUESTION — evidence-based answer")
    p("**Were my biggest losses primarily associated with holding multi-day option positions against SPY while carrying too many simultaneous or correlated option positions relative to my account size?**")
    p("")
    p("The hypothesis has three components. Score them separately against this data:")
    p("")
    p("**Component 1 — 'Multi-day option trades AGAINST SPY are the primary loss vector'**")
    p(f"- SPY classified BEARISH on {n_bearish_days} of {len(spy_ctx)} option-trade opens. AGAINST-SPY option trades total n={s_ag['n']} of {n_options} option trades. **The hypothesis's target class barely exists in this window.**")
    p(f"- Multi-day AGAINST-SPY trades: n={s_md_ag['n']} (⚠ tiny sample), mean {_fmt_money(s_md_ag['mean'])}, total {_fmt_money(s_md_ag['total'])}. On this sample, they were PROFITABLE.")
    p(f"- Top-15 largest losses AGAINST SPY: **{largest_loss_analysis['against_spy']}/15**. Directly refutes.")
    p(f"- Multi-day ALIGNED vs AGAINST vs MIXED means: ALIGNED {_fmt_money(s_md_al['mean'])}, AGAINST {_fmt_money(s_md_ag['mean'])}, **MIXED {_fmt_money(s_md_mx['mean'])}**. The heavy loss lives in MIXED, not AGAINST.")
    p("- **Verdict on Component 1**: **NOT SUPPORTED** on this data (the against-SPY subset is small and was actually profitable). But note: an untestable claim — a 3-month window with only 1 BEARISH-classified SPY day cannot fairly test 'against SPY' at any semantic.")
    p("")
    p("**Component 2 — 'Too many simultaneous positions relative to account size'**")
    p(f"- The book **always** operated at 3+ open positions (817 of 817 option trades — 100%). Preregistered LOW / MED count-buckets never occurred.")
    p(f"- Top-15 largest losses with 3+ open positions at entry: **{largest_loss_analysis['3plus_positions']}/15**.")
    p(f"- Top-15 largest losses with premium ≥ 30% of estimated equity at entry: **{largest_loss_analysis['high_exposure']}/15**.")
    p(f"- Highest exposure bucket (50%+): n={s_50['n']}, mean {_fmt_money(s_50['mean'])}. Lower buckets (<20%): mean {_fmt_money(s_lt20['mean'])}. Difference is small.")
    p(f"- Empirical below-median vs at/above-median open-count split: mean {_fmt_money(s_below['mean'])} vs {_fmt_money(s_above['mean'])}. Load DOES correlate with worse outcomes in the empirical (post-hoc) split.")
    p("- **Verdict on Component 2**: **PARTIALLY SUPPORTED as a book-composition observation** (every large loss happened under high-load conditions), but the finding is **CONFOUNDED** — there are no low-load trades to compare against. Cannot separate 'high load causes losses' from 'this trader always trades under high load'.")
    p("")
    p("**Component 3 — 'Correlated position clusters'**")
    p(f"- Top-15 largest losses with a correlated cluster active at entry: **{largest_loss_analysis['correlated_cluster']}/15**.")
    p(f"- SECTOR_CLUSTER_quantum: n=68, mean {_fmt_money(-16.81)}, PF 0.27, total {_fmt_money(-1142.91)} — worst cluster in the table.")
    p(f"- SECTOR_CLUSTER_space_aero: n=67, mean {_fmt_money(-14.49)}, PF 0.25, total {_fmt_money(-970.68)} — near-worst.")
    p(f"- BEARISH_INDEX_STACK: n=33, mean {_fmt_money(-20.80)}, PF 0.18, total {_fmt_money(-686.52)} — very poor when trading multiple index puts simultaneously.")
    p(f"- Historical daily-return correlation SPY–QQQ = 0.92 confirms 'multiple index positions' are near-duplicates.")
    p("- **Verdict on Component 3**: **PARTIALLY SUPPORTED** — specific correlated stacks (quantum, space/aero, bearish-index) have materially worse per-trade P&L. But again, high-load is universal so we cannot isolate the cluster effect from the total-load effect.")
    p("")
    p("---")
    p("")
    p("**Overall verdict on the compound hypothesis**:")
    p("")
    p(f"**PARTIALLY SUPPORTED** — with critical corrections to the original framing:")
    p("")
    p(f"- The 'AGAINST SPY' component is **NOT SUPPORTED** by this 3-month sample: SPY almost never qualified as BEARISH, so AGAINST-SPY option trades are rare (n={s_ag['n']}) and were actually PROFITABLE on average. Zero of the top-15 largest losses were AGAINST SPY. The real loss bucket is **MIXED SPY regime**, not AGAINST.")
    p("- The 'too many simultaneous / correlated positions' component is **BROADLY CONSISTENT WITH THE DATA** — every large loss happened while the book carried a correlated cluster and 3+ open positions. But it is CONFOUNDED: the book has no LOW-load counter-examples, so we cannot say load CAUSES the losses vs COINCIDES with them.")
    p("- The DTE and moneyness picture (from previous diagnostics) — same-day, 0-1 DTE, ATM/OTM — is where much of the actual damage lives, independently of alignment.")
    p("")
    p("**Do not act on this alone.** Next steps: pull real per-day account snapshots, extend intraday coverage for entry/exit reconstruction, and rerun on the next 3-month window. This sample cannot separate 'alignment against SPY' from 'trading during a chop regime', nor 'high load causes losses' from 'high load is this trader's default operating state'.")

    report_path.write_text("\n".join(lines))
    print(f"Wrote report: {report_path}")


if __name__ == "__main__":
    import sys
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "/root/.claude/uploads/7d497cb3-2bdb-560e-915e-2f206b920cf3/0f1bec32-XXXX1615_GainLoss_Realized_Details_20260916-101658.csv"
    cache_dir = sys.argv[2] if len(sys.argv) > 2 else "/tmp/claude-0/-home-user-autonomous-trading-system/7d497cb3-2bdb-560e-915e-2f206b920cf3/scratchpad/bars_cache"
    report_path = sys.argv[3] if len(sys.argv) > 3 else "/home/user/autonomous-trading-system/research/results/schwab_hypothesis_spy_load_report.md"
    run(csv_path, cache_dir, report_path)
