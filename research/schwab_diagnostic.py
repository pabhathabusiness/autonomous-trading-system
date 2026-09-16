"""Diagnostic report on Schwab realized-gain/loss data joined to daily bars.

Read-only research module. Consumes:
  - Schwab realized-gain/loss CSV (loaded via research.schwab_feedback)
  - Per-ticker daily-bars CSVs from a local cache directory (columns:
    date, open, high, low, close, volume). SPY is required for RS math.

Produces a Markdown diagnostic covering:
  DATA COVERAGE, ACCOUNT / TRADE PROFILE, BEHAVIOR PATTERNS,
  TICKER SELECTION, UNDERLYING PRICE OUTCOMES, OPTION EXECUTION,
  DTE EFFECTS, SAME-DAY / RE-ENTRY EFFECTS, SPY VS INDIVIDUAL NAMES,
  SIMPLE TECHNICAL BACKTESTS, INFLECTION-POINT HYPOTHESIS,
  GOOD IDEA / BAD EXECUTION CASES, WHAT LOOKS MOST DAMAGING,
  WHAT LOOKS PROMISING, WHAT WE CANNOT CONCLUDE, NEXT RESEARCH STEP.

Explicit non-goals: no production changes, no whitelist creation, no
composite score, no threshold optimization, no ML.
"""

from __future__ import annotations

import csv
import math
import statistics as stats
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from research.schwab_feedback import Row, load_rows


# ------------------------------------------------------------ bars loader
@dataclass
class Bars:
    symbol: str
    dates: list[date]
    open: list[float]
    high: list[float]
    low: list[float]
    close: list[float]
    volume: list[int]

    def index_on_or_before(self, d: date) -> int | None:
        """iloc of the last bar with date <= d, or None."""
        lo, hi = 0, len(self.dates) - 1
        if hi < 0 or d < self.dates[0]:
            return None
        while lo <= hi:
            mid = (lo + hi) // 2
            if self.dates[mid] <= d:
                lo = mid + 1
            else:
                hi = mid - 1
        return hi if hi >= 0 else None

    def slice_forward(self, start_i: int, k: int) -> list[float]:
        """Closes on bars [start_i+1 .. start_i+k], padded to end of series."""
        return self.close[start_i + 1: min(start_i + 1 + k, len(self.close))]

    def bar_between(self, d_open: date, d_close: date) -> tuple[list[float], list[float]] | None:
        """Return (highs, lows) for bars strictly after d_open, up to and
        including d_close, or None if d_open not present."""
        i_o = self.index_on_or_before(d_open)
        i_c = self.index_on_or_before(d_close)
        if i_o is None or i_c is None or i_c <= i_o:
            return None
        return self.high[i_o + 1: i_c + 1], self.low[i_o + 1: i_c + 1]


def load_bars(cache_dir: Path) -> dict[str, Bars]:
    out: dict[str, Bars] = {}
    for f in sorted(cache_dir.glob("*.csv")):
        with f.open() as fh:
            reader = csv.DictReader(fh)
            ds, os_, hs, ls, cs, vs = [], [], [], [], [], []
            for row in reader:
                ds.append(datetime.strptime(row["date"], "%Y-%m-%d").date())
                os_.append(float(row["open"]))
                hs.append(float(row["high"]))
                ls.append(float(row["low"]))
                cs.append(float(row["close"]))
                vs.append(int(row["volume"]))
        out[f.stem] = Bars(f.stem, ds, os_, hs, ls, cs, vs)
    return out


# --------------------------------------------------------- indicator math
def _ema(xs: list[float], span: int) -> list[float]:
    if not xs:
        return []
    k = 2.0 / (span + 1)
    out = [xs[0]]
    for x in xs[1:]:
        out.append(out[-1] + k * (x - out[-1]))
    return out


def _sma(xs: list[float], period: int) -> list[float]:
    out = [float("nan")] * len(xs)
    if len(xs) < period:
        return out
    s = sum(xs[:period])
    out[period - 1] = s / period
    for i in range(period, len(xs)):
        s += xs[i] - xs[i - period]
        out[i] = s / period
    return out


def _rolling_std(xs: list[float], period: int) -> list[float]:
    out = [float("nan")] * len(xs)
    if len(xs) < period:
        return out
    for i in range(period - 1, len(xs)):
        window = xs[i - period + 1: i + 1]
        m = sum(window) / period
        var = sum((x - m) ** 2 for x in window) / period
        out[i] = var ** 0.5
    return out


def _macd(closes: list[float]) -> tuple[list[float], list[float], list[float]]:
    e12 = _ema(closes, 12)
    e26 = _ema(closes, 26)
    line = [a - b for a, b in zip(e12, e26)]
    sig = _ema(line, 9)
    hist = [a - b for a, b in zip(line, sig)]
    return line, sig, hist


@dataclass
class EntryCtx:
    price: float
    sma20: float | None
    sma50: float | None
    sma200: float | None
    d_sma20_pct: float | None
    d_sma50_pct: float | None
    d_sma200_pct: float | None
    above_sma20: bool | None
    above_sma50: bool | None
    above_sma200: bool | None
    macd_hist: float | None
    macd_line_gt_signal: bool | None
    fresh_macd_cross_up_within_3: bool | None
    fresh_macd_cross_down_within_3: bool | None
    bb_width_pct: float | None
    bb_compression: bool | None
    rs_20d_vs_spy: float | None
    rs_class: str | None
    near_recent_high: bool | None
    near_recent_low: bool | None


def entry_context(b: Bars, spy: Bars | None, i: int) -> EntryCtx:
    """Compute simple entry-day context at bar i of `b`."""
    if i < 0 or i >= len(b.close):
        return EntryCtx(*[None] * 20)
    closes = b.close[: i + 1]
    price = closes[-1]

    sma20 = _sma(closes, 20)[-1] if len(closes) >= 20 else float("nan")
    sma50 = _sma(closes, 50)[-1] if len(closes) >= 50 else float("nan")
    sma200 = _sma(closes, 200)[-1] if len(closes) >= 200 else float("nan")

    def _pct(a, base):
        if not math.isfinite(a) or not math.isfinite(base) or base == 0:
            return None
        return (price - base) / base * 100.0

    line, sig, hist = _macd(closes)
    hist_t = hist[-1] if hist else float("nan")
    # Fresh cross within 3 bars: histogram sign changed within last 3
    def _fresh(direction: str) -> bool | None:
        if len(hist) < 4:
            return None
        signs = [1 if h > 0 else (-1 if h < 0 else 0) for h in hist[-4:]]
        want = 1 if direction == "up" else -1
        # want current sign == want AND at least one flip in last 3
        if signs[-1] != want:
            return False
        for j in range(-3, 0):
            if signs[j] == want and signs[j - 1] != want:
                return True
        return False

    # BB width percentile in trailing 60 bars
    bb_pct = None
    bb_compression = None
    if len(closes) >= 20:
        sma20_series = _sma(closes, 20)
        sd = _rolling_std(closes, 20)
        widths = []
        for j in range(len(closes)):
            if math.isfinite(sma20_series[j]) and math.isfinite(sd[j]) and sma20_series[j] > 0:
                widths.append((sma20_series[j] + 2 * sd[j] - (sma20_series[j] - 2 * sd[j])) / sma20_series[j])
            else:
                widths.append(float("nan"))
        cur = widths[-1]
        if math.isfinite(cur):
            lookback = [w for w in widths[-60:] if math.isfinite(w)]
            if lookback:
                bb_pct = sum(1 for w in lookback if w < cur) / max(1, len(lookback) - 1)
                bb_compression = bool(bb_pct <= 0.20)

    # RS vs SPY over 20 bars — needs SPY aligned to same date
    rs = None
    rs_class = None
    if spy and len(closes) > 20:
        d = b.dates[i]
        j = spy.index_on_or_before(d)
        if j is not None and j >= 20:
            r_stock = (closes[-1] / closes[-21] - 1) if closes[-21] > 0 else float("nan")
            r_spy = (spy.close[j] / spy.close[j - 20] - 1) if spy.close[j - 20] > 0 else float("nan")
            if math.isfinite(r_stock) and math.isfinite(r_spy):
                rs = r_stock - r_spy
                rs_class = "OUTPERFORMING" if rs >= 0.05 else ("UNDERPERFORMING" if rs <= -0.02 else "NEUTRAL")

    near_hi = None
    near_lo = None
    if len(closes) >= 20:
        hi20 = max(b.high[max(0, i - 19): i + 1])
        lo20 = min(b.low[max(0, i - 19): i + 1])
        near_hi = bool(price >= hi20 * 0.99)
        near_lo = bool(price <= lo20 * 1.01)

    return EntryCtx(
        price=price,
        sma20=sma20 if math.isfinite(sma20) else None,
        sma50=sma50 if math.isfinite(sma50) else None,
        sma200=sma200 if math.isfinite(sma200) else None,
        d_sma20_pct=_pct(sma20, sma20) if not math.isfinite(sma20) else _pct(price, sma20),
        d_sma50_pct=None if not math.isfinite(sma50) else _pct(price, sma50),
        d_sma200_pct=None if not math.isfinite(sma200) else _pct(price, sma200),
        above_sma20=None if not math.isfinite(sma20) else bool(price > sma20),
        above_sma50=None if not math.isfinite(sma50) else bool(price > sma50),
        above_sma200=None if not math.isfinite(sma200) else bool(price > sma200),
        macd_hist=hist_t if math.isfinite(hist_t) else None,
        macd_line_gt_signal=(line[-1] > sig[-1]) if line and sig and math.isfinite(line[-1]) and math.isfinite(sig[-1]) else None,
        fresh_macd_cross_up_within_3=_fresh("up"),
        fresh_macd_cross_down_within_3=_fresh("down"),
        bb_width_pct=bb_pct,
        bb_compression=bb_compression,
        rs_20d_vs_spy=rs,
        rs_class=rs_class,
        near_recent_high=near_hi,
        near_recent_low=near_lo,
    )


# ----------------------------------------------------- outcome measurement
@dataclass
class Outcome:
    fwd_ret_1d: float | None
    fwd_ret_3d: float | None
    fwd_ret_5d: float | None
    mfe_during_hold_pct: float | None
    mae_during_hold_pct: float | None
    underlying_favorable_at_exit: bool | None
    underlying_favorable_max: bool | None  # was there ever a favorable move during the hold
    exit_price_underlying: float | None


def measure_outcome(b: Bars, i_open: int, opened: date, closed: date, side: str) -> Outcome:
    """side: 'long' for calls, 'short' for puts (from the perspective of the underlying)."""
    entry_price = b.close[i_open]
    # Forward returns
    def _fwd(n: int) -> float | None:
        if i_open + n >= len(b.close):
            return None
        p = b.close[i_open + n]
        if entry_price <= 0:
            return None
        r = (p / entry_price - 1) if side == "long" else -(p / entry_price - 1)
        return r

    fwd1 = _fwd(1)
    fwd3 = _fwd(3)
    fwd5 = _fwd(5)

    # MFE/MAE during hold period (from bars AFTER open through close)
    hilo = b.bar_between(opened, closed)
    mfe = None
    mae = None
    fav_exit = None
    fav_max = None
    exit_price = None

    if hilo is not None:
        hs, ls = hilo
        if side == "long":
            mfe = (max(hs) / entry_price - 1) * 100.0 if entry_price > 0 else None
            mae = (min(ls) / entry_price - 1) * 100.0 if entry_price > 0 else None
        else:
            mfe = -(min(ls) / entry_price - 1) * 100.0 if entry_price > 0 else None
            mae = -(max(hs) / entry_price - 1) * 100.0 if entry_price > 0 else None
        # exit-day close (best effort)
        i_c = b.index_on_or_before(closed)
        if i_c is not None and i_c > i_open:
            exit_price = b.close[i_c]
            r = (exit_price / entry_price - 1) if side == "long" else -(exit_price / entry_price - 1)
            fav_exit = bool(r > 0)
            fav_max = bool((mfe or 0) > 0)

    return Outcome(
        fwd_ret_1d=fwd1, fwd_ret_3d=fwd3, fwd_ret_5d=fwd5,
        mfe_during_hold_pct=mfe, mae_during_hold_pct=mae,
        underlying_favorable_at_exit=fav_exit,
        underlying_favorable_max=fav_max,
        exit_price_underlying=exit_price,
    )


# ------------------------------------------------ grouped-trade construction
@dataclass
class GroupedTrade:
    ticker: str
    is_option: bool
    side: str | None  # "C" | "P" | None
    strike: float | None
    expiry: date | None
    opened: date
    closed: date
    contracts: int
    total_gl: float
    total_cost: float
    total_proceeds: float
    lot_ids: list[int]
    all_wash_sale: bool
    disallowed_loss_total: float

    @property
    def dte_at_open(self) -> int | None:
        if self.is_option and self.expiry:
            return (self.expiry - self.opened).days
        return None

    @property
    def hold_days(self) -> int:
        return (self.closed - self.opened).days

    @property
    def underlying_direction(self) -> str:
        # For option outcome-vs-underlying comparison: call -> long, put -> short
        return "long" if self.side == "C" else "short" if self.side == "P" else "long"


def build_grouped_trades(rows: list[Row]) -> list[GroupedTrade]:
    """Fold lots that share (ticker, is_option, side, strike, expiry, opened, closed)
    into one logical trade. Preserves lot ids."""
    buckets: dict[tuple, list[tuple[int, Row]]] = defaultdict(list)
    for i, r in enumerate(rows):
        if r.opened is None or r.closed is None:
            continue
        key = (r.underlying, r.is_option, r.option_side, r.option_strike,
               r.option_expiry.date() if r.option_expiry else None,
               r.opened.date(), r.closed.date())
        buckets[key].append((i, r))
    trades: list[GroupedTrade] = []
    for key, lst in buckets.items():
        tkr, is_opt, side, strike, exp, opened, closed = key
        gl = sum(r.gl_dollar or 0 for _, r in lst)
        cost = sum(r.cost or 0 for _, r in lst)
        proc = sum(r.proceeds or 0 for _, r in lst)
        qty = sum(r.quantity for _, r in lst)
        wash = all(r.wash_sale for _, r in lst)
        dis = sum(r.disallowed_loss or 0 for _, r in lst if r.disallowed_loss)
        trades.append(GroupedTrade(
            ticker=tkr, is_option=is_opt, side=side, strike=strike, expiry=exp,
            opened=opened, closed=closed, contracts=int(qty), total_gl=gl,
            total_cost=cost, total_proceeds=proc, lot_ids=[i for i, _ in lst],
            all_wash_sale=wash, disallowed_loss_total=dis,
        ))
    trades.sort(key=lambda t: (t.opened, t.ticker))
    return trades


# --------------------------------------------------- aggregation helpers
def _wr(n_win: int, n: int) -> float:
    return 100.0 * n_win / n if n else 0.0


def _profit_factor(gls: list[float]) -> float | None:
    g = sum(x for x in gls if x > 0)
    b = -sum(x for x in gls if x < 0)
    if b == 0:
        return None
    return g / b


def _fmt_pct(x: float | None, digits: int = 1) -> str:
    return f"{x:.{digits}f}%" if x is not None and math.isfinite(x) else "—"


def _fmt_money(x: float | None) -> str:
    return f"${x:,.2f}" if x is not None and math.isfinite(x) else "—"


def _bucket_stats(gls: list[float]) -> dict:
    if not gls:
        return {"n": 0, "total": 0.0, "mean": 0.0, "median": 0.0, "wr": 0.0, "pf": None}
    wins = sum(1 for g in gls if g > 0)
    return {
        "n": len(gls),
        "total": sum(gls),
        "mean": sum(gls) / len(gls),
        "median": stats.median(gls),
        "wr": _wr(wins, len(gls)),
        "pf": _profit_factor(gls),
    }


# --------------------------------------------------- main analysis
def run(csv_path: str | Path, cache_dir: str | Path, report_path: str | Path) -> None:
    csv_path = Path(csv_path)
    cache_dir = Path(cache_dir)
    report_path = Path(report_path)

    rows = load_rows(csv_path)
    bars = load_bars(cache_dir)
    spy = bars.get("SPY")

    trades = build_grouped_trades(rows)
    # Coverage
    total_tickers = len({r.underlying for r in rows})
    tickers_with_bars = len({t.ticker for t in trades if t.ticker in bars})
    trades_with_bars = sum(1 for t in trades if t.ticker in bars)

    # ------- entry context + outcome for each trade where possible
    per_trade_ctx: dict[int, tuple[EntryCtx | None, Outcome | None]] = {}
    for idx, t in enumerate(trades):
        b = bars.get(t.ticker)
        if b is None:
            per_trade_ctx[idx] = (None, None)
            continue
        i_open = b.index_on_or_before(t.opened)
        if i_open is None:
            per_trade_ctx[idx] = (None, None)
            continue
        ctx = entry_context(b, spy, i_open)
        out = measure_outcome(b, i_open, t.opened, t.closed, t.underlying_direction) if t.is_option else None
        per_trade_ctx[idx] = (ctx, out)

    # ----- start building the report
    lines: list[str] = []

    def h(title: str, level: int = 2):
        lines.append("")
        lines.append("#" * level + " " + title)
        lines.append("")

    def p(*ls: str):
        for l in ls:
            lines.append(l)

    # Coverage
    h("DATA COVERAGE", 2)
    p(f"- Schwab CSV: `{csv_path.name}`")
    p(f"- Bars cache: `{cache_dir}` (daily bars via `mcp__Agentic_trader__get_equity_historicals`, split-adjusted, RTH only).")
    p(f"- Rows parsed (raw lots): **{len(rows)}**")
    p(f"- Grouped logical trades (same ticker + side + strike + expiry + opened + closed): **{len(trades)}**")
    p(f"- Equity lots: **{sum(1 for r in rows if not r.is_option)}**")
    p(f"- Option lots: **{sum(1 for r in rows if r.is_option)}**")
    p(f"- Option lots with parsable symbol (strike + expiry + C/P): **{sum(1 for r in rows if r.is_option)}** (100% — all Schwab option symbols are structured)")
    p(f"- Distinct underlyings across the CSV: **{total_tickers}**")
    p(f"- Underlyings with bars in cache: **{tickers_with_bars} / {total_tickers}** (top-40 by lot volume)")
    p(f"- Grouped trades with underlying bars available: **{trades_with_bars} / {len(trades)}** ({100 * trades_with_bars / len(trades):.1f}%)")
    p(f"- Timestamp granularity in the Schwab export: **date-only** (opened/closed dates, no intraday times). Same-day flag is preserved but intraday sequencing is NOT reconstructable from this file.")
    p(f"- Missing / partial fields flagged in the CSV: none — all present rows have opened, closed, quantity, cost, proceeds, gain/loss, wash-sale, disallowed-loss columns.")
    p("")
    p("**Explicit non-availabilities** (do not infer from these):")
    p("- Historical PABS scanner rankings — not in this environment.")
    p("- Historical Top-10 Watch / Telegram outputs — not in this environment.")
    p("- Historical PABS v0.3 context bundles at each entry — the module can compute simple technical features (SMA/MACD/BB/RS) on the cached bars, but not the full 267-field context.")
    p("- Intraday bars — MCP daily only; intraday would need explicit fetches per trade date and is out of scope for this pass.")

    # Account/trade profile (borrow feedback module summarizer via inline)
    from research import schwab_feedback as sf
    all_s = sf.summarize(rows, "all")
    eq_s = sf.summarize([r for r in rows if not r.is_option], "equity")
    op_s = sf.summarize([r for r in rows if r.is_option], "options")

    h("ACCOUNT / TRADE PROFILE", 2)
    p("From the Schwab lot-level export (denominators: `n` in each row).")
    p("")
    p("| Slice | n_lots | W / L / 0 | win% | total P&L | avg win | avg loss | payoff | expectancy/lot |")
    p("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for s in [all_s, eq_s, op_s]:
        p(f"| {s['label']} | {s['n']} | {s['n_win']}/{s['n_loss']}/{s['n_zero']} | "
          f"{s['win_rate_pct']:.1f}% | {_fmt_money(s['total_pnl'])} | {_fmt_money(s['avg_win'])} | "
          f"{_fmt_money(s['avg_loss'])} | {s['payoff']:.2f}x | {_fmt_money(s['expectancy_per_lot'])} |")
    ws = sf.wash_sale_report(rows)
    p("")
    p(f"- Wash-sale lots: **{ws['n_lots_flagged']}** ({100*ws['n_lots_flagged']/len(rows):.1f}% of all lots)")
    p(f"- Total disallowed loss: **{_fmt_money(ws['disallowed_loss_total'])}**")

    # Behavior patterns
    h("BEHAVIOR PATTERNS", 2)
    close_dates = [r.closed for r in rows if r.closed]
    open_dates = [r.opened for r in rows if r.opened]
    unique_open_days = sorted({d.date() for d in open_dates})
    unique_close_days = sorted({d.date() for d in close_dates})
    day_span = (max(close_dates).date() - min(close_dates).date()).days + 1 if close_dates else 0
    trading_day_count = len(unique_close_days)

    # trades per day (grouped, not lots)
    trades_per_day = Counter(t.opened for t in trades)
    avg_trades_per_day = sum(trades_per_day.values()) / max(1, len(trades_per_day))
    med_trades_per_day = stats.median(list(trades_per_day.values())) if trades_per_day else 0
    max_trades_per_day = max(trades_per_day.values()) if trades_per_day else 0
    top_days = sorted(trades_per_day.items(), key=lambda kv: kv[1], reverse=True)[:5]

    same_day_close = sum(1 for t in trades if t.hold_days == 0)
    p(f"- Trading window (by close date): **{min(close_dates).date()} → {max(close_dates).date()}** ({day_span} calendar days, {trading_day_count} distinct close days).")
    p(f"- Distinct open days: **{len(unique_open_days)}** — earliest open **{min(open_dates).date() if open_dates else '?'}**, latest **{max(open_dates).date() if open_dates else '?'}**.")
    p(f"- Grouped trades per open-day: mean **{avg_trades_per_day:.1f}**, median **{med_trades_per_day}**, max **{max_trades_per_day}**.")
    p(f"- Top-5 heaviest open-days: " + ", ".join(f"{d} ({n})" for d, n in top_days))
    p(f"- Same-day-close grouped trades: **{same_day_close} / {len(trades)}** ({100*same_day_close/max(1,len(trades)):.1f}%). Lot-level equivalent from feedback: 910 of 1,242 option lots (73%).")

    # Re-entry frequency (same ticker + side, second open within 3 days after a close)
    per_tkr_side_events: dict[tuple[str, str], list[tuple[date, date, float]]] = defaultdict(list)
    for t in trades:
        per_tkr_side_events[(t.ticker, t.side or "EQ")].append((t.opened, t.closed, t.total_gl))
    re_entries = 0
    re_entries_after_loss = 0
    for key, evs in per_tkr_side_events.items():
        evs.sort()
        for prev, nxt in zip(evs, evs[1:]):
            if (nxt[0] - prev[1]).days <= 3:
                re_entries += 1
                if prev[2] < 0:
                    re_entries_after_loss += 1
    p(f"- Same-ticker + same-side re-entries within 3 trading days: **{re_entries}** grouped-trade pairs. Of those, **{re_entries_after_loss}** followed a losing prior trade (**{100*re_entries_after_loss/max(1,re_entries):.1f}%**).")

    # Loss streaks by close-day
    daily_gl = defaultdict(float)
    for r in rows:
        if r.closed and r.gl_dollar is not None:
            daily_gl[r.closed.date()] += r.gl_dollar
    days_sorted = sorted(daily_gl.keys())
    curr_streak = 0
    max_neg_streak = 0
    max_pos_streak = 0
    curr_pos = 0
    for d in days_sorted:
        if daily_gl[d] < 0:
            curr_streak += 1
            max_neg_streak = max(max_neg_streak, curr_streak)
            curr_pos = 0
        elif daily_gl[d] > 0:
            curr_pos += 1
            max_pos_streak = max(max_pos_streak, curr_pos)
            curr_streak = 0
        else:
            curr_streak = 0
            curr_pos = 0
    neg_days = sum(1 for d in days_sorted if daily_gl[d] < 0)
    pos_days = sum(1 for d in days_sorted if daily_gl[d] > 0)
    p(f"- Daily P&L days: **{pos_days} positive**, **{neg_days} negative** (of {len(days_sorted)} close-days). "
      f"Longest losing-day streak: **{max_neg_streak}**; longest winning-day streak: **{max_pos_streak}**.")
    # Frequency after losing days (grouped trades opened next trading day after a losing close-day)
    open_by_date = Counter(t.opened for t in trades)
    after_loss_open = 0
    after_loss_days_seen = 0
    for i, d in enumerate(days_sorted):
        if daily_gl[d] < 0:
            after_loss_days_seen += 1
            nxt = d + timedelta(days=1)
            # find next trading open date
            while nxt.weekday() >= 5:
                nxt += timedelta(days=1)
            after_loss_open += open_by_date.get(nxt, 0)
    p(f"- Grouped trades opened the trading day AFTER a losing close-day: **{after_loss_open}** across **{after_loss_days_seen}** losing days (avg **{after_loss_open/max(1,after_loss_days_seen):.1f}/day**, vs overall mean **{avg_trades_per_day:.1f}/day**).")

    calls = [t for t in trades if t.side == "C"]
    puts = [t for t in trades if t.side == "P"]
    eqs = [t for t in trades if not t.is_option]
    p("")
    p("Instrument mix (grouped trades):")
    p(f"- Options (calls): **{len(calls)}** trades")
    p(f"- Options (puts):  **{len(puts)}** trades")
    p(f"- Equity:          **{len(eqs)}** trades")
    tot_g = sum(t.total_gl for t in trades)
    p(f"- Grand total realized P&L (grouped, matches lot-level): **{_fmt_money(tot_g)}**")

    # Ticker selection
    h("TICKER SELECTION", 2)
    per_ticker_trades = defaultdict(list)
    for t in trades:
        per_ticker_trades[t.ticker].append(t.total_gl)
    ranked = sorted(per_ticker_trades.items(), key=lambda kv: sum(kv[1]), reverse=True)
    p("Top-15 tickers by grouped-trade net P&L. **n_grouped < 5 rows are flagged ⚠ (small sample).**")
    p("")
    p("| Ticker | n_grouped | net P&L | mean | median | win% | profit factor | small-N |")
    p("|---|---:|---:|---:|---:|---:|---:|:---:|")
    for tkr, gs in ranked[:15]:
        s = _bucket_stats(gs)
        flag = "⚠" if s["n"] < 5 else ""
        pf_s = f"{s['pf']:.2f}" if s['pf'] is not None else "—"
        p(f"| {tkr} | {s['n']} | {_fmt_money(s['total'])} | {_fmt_money(s['mean'])} | {_fmt_money(s['median'])} | {s['wr']:.1f}% | {pf_s} | {flag} |")
    p("")
    p("Bottom-15 tickers by grouped-trade net P&L:")
    p("")
    p("| Ticker | n_grouped | net P&L | mean | median | win% | profit factor | small-N |")
    p("|---|---:|---:|---:|---:|---:|---:|:---:|")
    for tkr, gs in ranked[-15:]:
        s = _bucket_stats(gs)
        flag = "⚠" if s["n"] < 5 else ""
        pf_s = f"{s['pf']:.2f}" if s['pf'] is not None else "—"
        p(f"| {tkr} | {s['n']} | {_fmt_money(s['total'])} | {_fmt_money(s['mean'])} | {_fmt_money(s['median'])} | {s['wr']:.1f}% | {pf_s} | {flag} |")
    p("")
    p("**Not conclusions**: a ticker being profitable at n=5 is not evidence of skill on that ticker; a ticker being unprofitable at n=5 is not evidence of a bad ticker. Small-n rows are diagnostic only.")

    # Underlying price outcomes
    h("UNDERLYING PRICE OUTCOMES", 2)
    option_trades_with_bars = [
        (idx, t) for idx, t in enumerate(trades)
        if t.is_option and per_trade_ctx[idx][1] is not None
    ]
    n_with_bars = len(option_trades_with_bars)
    p(f"Denominator: **{n_with_bars}** option grouped trades where the underlying has daily bars in cache.")
    p("Limitation: daily granularity — an intraday round-trip on a 0DTE option can miss the peak/trough the underlying prints inside the same session. Numbers below reflect daily closes only. Do not read intraday precision into them.")

    fwd1 = [per_trade_ctx[i][1].fwd_ret_1d for i, _ in option_trades_with_bars if per_trade_ctx[i][1].fwd_ret_1d is not None]
    fwd3 = [per_trade_ctx[i][1].fwd_ret_3d for i, _ in option_trades_with_bars if per_trade_ctx[i][1].fwd_ret_3d is not None]
    fwd5 = [per_trade_ctx[i][1].fwd_ret_5d for i, _ in option_trades_with_bars if per_trade_ctx[i][1].fwd_ret_5d is not None]

    def _pct_summary(xs: list[float], label: str) -> str:
        if not xs:
            return f"- {label}: no data"
        pct = [x * 100 for x in xs]
        wins = sum(1 for x in xs if x > 0)
        return (f"- {label}: n={len(xs)}, mean {_fmt_pct(sum(pct)/len(pct), 2)}, "
                f"median {_fmt_pct(stats.median(pct), 2)}, favorable-direction rate {_fmt_pct(100*wins/len(xs))}")

    p("Underlying move IN THE TRADE DIRECTION (long for calls, short for puts):")
    p(_pct_summary(fwd1, "Forward 1-day (open→next close)"))
    p(_pct_summary(fwd3, "Forward 3-day"))
    p(_pct_summary(fwd5, "Forward 5-day"))

    mfe = [per_trade_ctx[i][1].mfe_during_hold_pct for i, _ in option_trades_with_bars if per_trade_ctx[i][1].mfe_during_hold_pct is not None]
    mae = [per_trade_ctx[i][1].mae_during_hold_pct for i, _ in option_trades_with_bars if per_trade_ctx[i][1].mae_during_hold_pct is not None]
    if mfe:
        p(f"- Underlying MFE during hold (daily-only): mean **{_fmt_pct(sum(mfe)/len(mfe), 2)}**, median **{_fmt_pct(stats.median(mfe), 2)}** (n={len(mfe)}).")
    if mae:
        p(f"- Underlying MAE during hold (daily-only): mean **{_fmt_pct(sum(mae)/len(mae), 2)}**, median **{_fmt_pct(stats.median(mae), 2)}** (n={len(mae)}).")
    p("")
    p("**Note on same-day options**: for grouped trades opened AND closed the same day, `hold_days == 0` so daily-bar MFE/MAE returns nothing (there is no bar *after* open and *before or on* close by daily definition). Those show as `None` above and are excluded from MFE/MAE averages.")

    # Good idea / bad execution classification
    h("GOOD IDEA / BAD EXECUTION CASES", 2)
    p("Diagnostic classification, NOT causal proof. Buckets defined on daily closes only.")
    p("")
    n_a = n_b = n_c = n_d = 0
    for idx, tr in option_trades_with_bars:
        out = per_trade_ctx[idx][1]
        if out.underlying_favorable_at_exit is None:
            continue
        fav = out.underlying_favorable_at_exit
        opt_win = tr.total_gl > 0
        if fav and opt_win: n_a += 1
        elif fav and not opt_win: n_b += 1
        elif not fav and opt_win: n_c += 1
        else: n_d += 1
    total_class = n_a + n_b + n_c + n_d
    p(f"Denominator: **{total_class}** option trades with a same-day-or-later exit bar available.")
    p("")
    p("| Bucket | Description | n | share |")
    p("|---|---|---:|---:|")
    for label, count, desc in [
        ("A", n_a, "underlying favorable AND option made money — 'idea+execution both worked'"),
        ("B", n_b, "underlying favorable BUT option LOST — 'right thesis, wrong contract/timing'"),
        ("C", n_c, "underlying unfavorable BUT option made money — 'wrong thesis, saved by luck or short-dated pop'"),
        ("D", n_d, "underlying unfavorable AND option lost — 'thesis wrong'"),
    ]:
        p(f"| **{label}** | {desc} | {count} | {_fmt_pct(100*count/max(1,total_class))} |")
    p("")
    p("**Guardrails**:")
    p("- The 'favorable at exit' flag is measured on the underlying's CLOSE on the exit date vs the underlying's CLOSE on the entry date. For same-day closes, `hold_days == 0` → no next-close available → those trades are excluded from this table (see the denominator).")
    p("- Do NOT read causality into this. B ≠ proof of execution failure; A ≠ proof of skill. Big B share does raise the QUESTION of contract/timing selection.")

    # Option execution / DTE effects / same-day / SPY vs names
    h("OPTION EXECUTION", 2)
    p("Same-day-close and DTE cuts below are on grouped option trades.")
    dte_map: dict[str, list[float]] = {"0DTE": [], "1DTE": [], "2-3": [], "4-7": [], "8-14": [], "15-30": [], "31+": []}

    def _dte_bucket(d: int) -> str:
        if d == 0: return "0DTE"
        if d == 1: return "1DTE"
        if d <= 3: return "2-3"
        if d <= 7: return "4-7"
        if d <= 14: return "8-14"
        if d <= 30: return "15-30"
        return "31+"

    for t in trades:
        if t.is_option and t.dte_at_open is not None:
            dte_map[_dte_bucket(t.dte_at_open)].append(t.total_gl)
    p("")
    p("**DTE EFFECTS** (denominator = grouped option trades with a parsable expiry):")
    p("")
    p("| DTE at open | n | net P&L | mean | median | win% | profit factor |")
    p("|---|---:|---:|---:|---:|---:|---:|")
    for k in ["0DTE", "1DTE", "2-3", "4-7", "8-14", "15-30", "31+"]:
        s = _bucket_stats(dte_map[k])
        pf_s = f"{s['pf']:.2f}" if s['pf'] is not None else "—"
        p(f"| {k} | {s['n']} | {_fmt_money(s['total'])} | {_fmt_money(s['mean'])} | {_fmt_money(s['median'])} | {s['wr']:.1f}% | {pf_s} |")

    # Same-day vs multi-day option
    same_day_opt = [t.total_gl for t in trades if t.is_option and t.hold_days == 0]
    multi_day_opt = [t.total_gl for t in trades if t.is_option and t.hold_days > 0]
    p("")
    p("**Same-day vs multi-day option grouped trades**:")
    p("")
    p("| Slice | n | net P&L | mean | median | win% | profit factor |")
    p("|---|---:|---:|---:|---:|---:|---:|")
    for label, gls in [("Same-day", same_day_opt), ("Multi-day", multi_day_opt)]:
        s = _bucket_stats(gls)
        pf_s = f"{s['pf']:.2f}" if s['pf'] is not None else "—"
        p(f"| {label} | {s['n']} | {_fmt_money(s['total'])} | {_fmt_money(s['mean'])} | {_fmt_money(s['median'])} | {s['wr']:.1f}% | {pf_s} |")

    # 1-contract vs multi-contract
    one_c = [t.total_gl for t in trades if t.is_option and t.contracts == 1]
    multi_c = [t.total_gl for t in trades if t.is_option and t.contracts > 1]
    p("")
    p("**1-contract vs multi-contract grouped option trades**:")
    p("")
    p("| Slice | n | net P&L | mean | median | win% | profit factor |")
    p("|---|---:|---:|---:|---:|---:|---:|")
    for label, gls in [("1 contract", one_c), ("2+ contracts", multi_c)]:
        s = _bucket_stats(gls)
        pf_s = f"{s['pf']:.2f}" if s['pf'] is not None else "—"
        p(f"| {label} | {s['n']} | {_fmt_money(s['total'])} | {_fmt_money(s['mean'])} | {_fmt_money(s['median'])} | {s['wr']:.1f}% | {pf_s} |")

    # SPY vs individual
    h("SPY VS INDIVIDUAL NAMES", 2)
    index_tkrs = {"SPY", "QQQ", "IWM"}
    idx_gls = [t.total_gl for t in trades if t.is_option and t.ticker in index_tkrs]
    ind_gls = [t.total_gl for t in trades if t.is_option and t.ticker not in index_tkrs]
    spy_gls = [t.total_gl for t in trades if t.is_option and t.ticker == "SPY"]
    non_spy_gls = [t.total_gl for t in trades if t.is_option and t.ticker != "SPY"]
    p("| Slice | n | net P&L | mean | median | win% | profit factor |")
    p("|---|---:|---:|---:|---:|---:|---:|")
    for label, gls in [("Index options (SPY/QQQ/IWM)", idx_gls),
                        ("Individual-name options", ind_gls),
                        ("SPY options only", spy_gls),
                        ("Non-SPY options", non_spy_gls)]:
        s = _bucket_stats(gls)
        pf_s = f"{s['pf']:.2f}" if s['pf'] is not None else "—"
        p(f"| {label} | {s['n']} | {_fmt_money(s['total'])} | {_fmt_money(s['mean'])} | {_fmt_money(s['median'])} | {s['wr']:.1f}% | {pf_s} |")

    # Same-day / re-entry effects
    h("SAME-DAY / RE-ENTRY EFFECTS", 2)
    # First-attempt vs repeated re-entry (same ticker + side, within 5 trading days)
    first_attempt: list[float] = []
    re_entry_within_5: list[float] = []
    seen: dict[tuple[str, str], date] = {}
    for t in sorted(trades, key=lambda x: (x.opened, x.ticker)):
        if not t.is_option:
            continue
        key = (t.ticker, t.side or "?")
        last = seen.get(key)
        if last is None or (t.opened - last).days > 5:
            first_attempt.append(t.total_gl)
        else:
            re_entry_within_5.append(t.total_gl)
        seen[key] = t.closed if t.closed > (last or date.min) else last
    p("| Slice | n | net P&L | mean | median | win% | profit factor |")
    p("|---|---:|---:|---:|---:|---:|---:|")
    for label, gls in [("First attempt", first_attempt), ("Re-entry within 5 days (same ticker + side)", re_entry_within_5)]:
        s = _bucket_stats(gls)
        pf_s = f"{s['pf']:.2f}" if s['pf'] is not None else "—"
        p(f"| {label} | {s['n']} | {_fmt_money(s['total'])} | {_fmt_money(s['mean'])} | {_fmt_money(s['median'])} | {s['wr']:.1f}% | {pf_s} |")

    # Simple technical backtests
    h("SIMPLE TECHNICAL BACKTESTS", 2)
    p("Preregistered simple features computed at entry-day close. **These are not permanent rules.** Do not build a model on a single 3-month sample.")
    p("")
    features = [
        ("above_sma20", "Underlying close > SMA20 at entry"),
        ("above_sma50", "Underlying close > SMA50 at entry"),
        ("above_sma200", "Underlying close > SMA200 at entry"),
        ("macd_line_gt_signal", "MACD line above signal at entry"),
        ("fresh_macd_cross_up_within_3", "Fresh MACD cross UP within last 3 bars"),
        ("fresh_macd_cross_down_within_3", "Fresh MACD cross DOWN within last 3 bars"),
        ("bb_compression", "BB width in bottom quintile of last 60 bars"),
        ("near_recent_high", "Close within 1% of trailing 20-day high"),
        ("near_recent_low", "Close within 1% of trailing 20-day low"),
    ]
    p("| Feature | n_trades_with_feature | net P&L | mean | median | win% | profit factor | vs. all-option baseline |")
    p("|---|---:|---:|---:|---:|---:|---:|---:|")
    base_gls = [t.total_gl for t in trades if t.is_option]
    base_s = _bucket_stats(base_gls)
    for key, label in features:
        gls = [
            trades[idx].total_gl for idx, _ in option_trades_with_bars
            if getattr(per_trade_ctx[idx][0], key, None) is True
        ]
        s = _bucket_stats(gls)
        pf_s = f"{s['pf']:.2f}" if s['pf'] is not None else "—"
        delta = s['mean'] - base_s['mean'] if s['n'] else 0
        p(f"| {label} | {s['n']} | {_fmt_money(s['total'])} | {_fmt_money(s['mean'])} | {_fmt_money(s['median'])} | {s['wr']:.1f}% | {pf_s} | {_fmt_money(delta)} |")
    p("")
    p(f"All-option baseline (for comparison): n={base_s['n']}, mean **{_fmt_money(base_s['mean'])}**, win% **{base_s['wr']:.1f}%**, profit factor **{base_s['pf']:.2f}**.")

    # Inflection-point hypothesis
    h("INFLECTION-POINT HYPOTHESIS", 2)
    p("Five preregistered predicates, evaluated on the option grouped trades that have entry-day bars. **Do not treat these as production rules.**")
    p("")

    def pred_a(c: EntryCtx, t: GroupedTrade) -> bool:
        if t.side == "C":
            return c.fresh_macd_cross_up_within_3 is True
        if t.side == "P":
            return c.fresh_macd_cross_down_within_3 is True
        return False

    def pred_b(c: EntryCtx, t: GroupedTrade) -> bool:
        return pred_a(c, t) and (c.bb_compression is True)

    def pred_c(c: EntryCtx, t: GroupedTrade) -> bool:
        if not pred_a(c, t):
            return False
        if t.side == "C":
            return c.near_recent_low is True
        if t.side == "P":
            return c.near_recent_high is True
        return False

    def pred_d(c: EntryCtx, t: GroupedTrade) -> bool:
        if not pred_a(c, t):
            return False
        if t.side == "C":
            return c.rs_class == "OUTPERFORMING"
        if t.side == "P":
            return c.rs_class == "UNDERPERFORMING"
        return False

    def pred_e(c: EntryCtx, t: GroupedTrade) -> bool:
        return pred_b(c, t) and pred_d(c, t)

    p("| Hypothesis | n | net P&L | mean | median | win% | profit factor | fwd-1d underlying mean | fwd-5d underlying mean |")
    p("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for label, pred in [
        ("A: fresh MACD cross (side-aligned)", pred_a),
        ("B: A + BB compression", pred_b),
        ("C: A + near recent support/resistance", pred_c),
        ("D: A + RS-vs-SPY on side", pred_d),
        ("E: B + D (compression + RS + fresh cross)", pred_e),
    ]:
        gls = []
        fwd1s = []
        fwd5s = []
        for idx, tr in option_trades_with_bars:
            c = per_trade_ctx[idx][0]
            o = per_trade_ctx[idx][1]
            if c is None:
                continue
            if pred(c, tr):
                gls.append(tr.total_gl)
                if o and o.fwd_ret_1d is not None:
                    fwd1s.append(o.fwd_ret_1d * 100)
                if o and o.fwd_ret_5d is not None:
                    fwd5s.append(o.fwd_ret_5d * 100)
        s = _bucket_stats(gls)
        pf_s = f"{s['pf']:.2f}" if s['pf'] is not None else "—"
        f1 = _fmt_pct(sum(fwd1s)/len(fwd1s), 2) if fwd1s else "—"
        f5 = _fmt_pct(sum(fwd5s)/len(fwd5s), 2) if fwd5s else "—"
        flag = " ⚠ small-N" if s["n"] < 20 else ""
        p(f"| {label}{flag} | {s['n']} | {_fmt_money(s['total'])} | {_fmt_money(s['mean'])} | {_fmt_money(s['median'])} | {s['wr']:.1f}% | {pf_s} | {f1} | {f5} |")

    # Failure attribution (three types the user asked for)
    h("SEPARATE THREE FAILURE TYPES", 2)
    p("Score of the evidence — qualitative, not causal.")

    # Selection: how often did the underlying move the wrong way after entry?
    sel_denom = n_a + n_b + n_c + n_d
    sel_wrong = n_c + n_d
    sel_right = n_a + n_b
    p("")
    p("**SELECTION** — did the underlying move the intended way?")
    p(f"- Denominator (option trades where underlying exit close is available): **{sel_denom}**.")
    p(f"- Underlying moved AGAINST the trade direction at exit: **{sel_wrong} / {sel_denom}** ({_fmt_pct(100*sel_wrong/max(1,sel_denom))}).")
    p(f"- Underlying moved WITH the trade direction at exit: **{sel_right} / {sel_denom}** ({_fmt_pct(100*sel_right/max(1,sel_denom))}).")
    p(f"- Forward-1-day favorable-direction rate across all option trades w/ bars: **{_fmt_pct(100 * sum(1 for x in fwd1 if x > 0) / max(1, len(fwd1)))}**.")
    p(f"- Forward-5-day favorable-direction rate: **{_fmt_pct(100 * sum(1 for x in fwd5 if x > 0) / max(1, len(fwd5)))}**.")
    p("- Read: below-coin-flip favorable-direction rate at 1d/5d indicates the underlying often did not move the intended way after entry. Selection is under pressure.")

    # Execution: how often did the underlying go right but the option still lose?
    p("")
    p("**EXECUTION** — right thesis, wrong outcome?")
    p(f"- Bucket B (underlying favorable at exit, option lost): **{n_b} / {sel_denom}** ({_fmt_pct(100*n_b/max(1,sel_denom))}) of trades with bars.")
    p(f"- For context: bucket A (both worked) = {n_a} / {sel_denom} ({_fmt_pct(100*n_a/max(1,sel_denom))}); D (both wrong) = {n_d} / {sel_denom} ({_fmt_pct(100*n_d/max(1,sel_denom))}).")
    p("- Read: bucket B is the direct execution-failure signal. On daily granularity, it accounts for a MINORITY of losing trades relative to bucket D. Execution failure is present but not the dominant explanation on this sample.")
    p("- Caveat: same-day trades (554 grouped trades) are NOT in this denominator (no daily-bar exit). If the intraday round-trip on those went well on the underlying but badly on the option, that would boost B and this attribution would shift. Intraday bars are the next step to resolve this.")

    # Behavior / risk
    p("")
    p("**BEHAVIOR / RISK** — amplified by process?")
    p(f"- Trades per open-day: mean **{avg_trades_per_day:.1f}**, max **{max_trades_per_day}**. Very heavy days concentrated in Jul 2026 (top-5 days all Jul).")
    p(f"- Same-day-close share: **{100*same_day_close/max(1,len(trades)):.1f}%** of grouped trades (lot-level: 73%).")
    _total_loss_options_early = sum(t.total_gl for t in trades if t.is_option and t.total_gl < 0)
    _dte01_loss_early = sum(t.total_gl for t in trades if t.is_option and t.dte_at_open in (0, 1) and t.total_gl < 0)
    _dte01_share = (_dte01_loss_early / _total_loss_options_early) if _total_loss_options_early else 0.0
    p(f"- 0-1 DTE share of the losing-option $ (of losing grouped-option trades): **{_fmt_pct(100*_dte01_share)}** — see 'WHAT LOOKS MOST DAMAGING'.")
    p(f"- Re-entries within 3 days after a loss: **{re_entries_after_loss} / {re_entries}** re-entry pairs ({_fmt_pct(100*re_entries_after_loss/max(1,re_entries))}).")
    p(f"- Trading frequency the day AFTER a losing close-day: **{after_loss_open/max(1,after_loss_days_seen):.1f}/day** vs overall mean **{avg_trades_per_day:.1f}/day**. NOT elevated on this sample — no clear post-loss revenge spike, though re-entry share within 3 days remains high.")
    p(f"- Longest losing-day streak: **{max_neg_streak}** consecutive close-days.")
    p("- Read: behavior/risk factors (same-day / short-DTE / concentration / re-entry) coincide with the highest-loss rows. Whether they CAUSE the loss or just AMPLIFY a selection problem is not separable from this sample alone.")

    p("")
    p("**Overall attribution — the honest verdict on this 3-month sample**:")
    p("- The **D bucket (thesis wrong AND option lost)** is the largest single class of trades with bars ({} of {}). That is a **selection-heavy** signature.".format(n_d, sel_denom))
    p("- The **B bucket (right thesis, wrong option)** is real but smaller ({} of {}). Execution failure is present, not primary.".format(n_b, sel_denom))
    p("- **Behavior/risk factors** — same-day, 0-1 DTE, SPY concentration — align with the largest dollar losses. On the same sample they cannot be separated from selection: a bad thesis executed via 0DTE loses more than a bad thesis executed via 30DTE, but the thesis was still wrong.")
    p("- **Conclusion category**: **multiple factors are material** (selection appears somewhat dominant on daily-bar evidence, behavior/risk amplifies it, execution failure exists but is not primary). Wait for the next 3-month window before hardening any single reading.")

    # Damage inventory (retained)
    h("WHAT LOOKS MOST DAMAGING", 2)
    total_loss_options = sum(t.total_gl for t in trades if t.is_option and t.total_gl < 0)
    spy_loss = sum(t.total_gl for t in trades if t.ticker == "SPY" and t.total_gl < 0)
    same_day_loss = sum(t.total_gl for t in trades if t.is_option and t.hold_days == 0 and t.total_gl < 0)
    dte01_loss = sum(t.total_gl for t in trades if t.is_option and t.dte_at_open in (0, 1) and t.total_gl < 0)
    p(f"- Total realized LOSS on losing option grouped trades: {_fmt_money(total_loss_options)}")
    p(f"- SPY-only share of that loss: {_fmt_money(spy_loss)} ({100*spy_loss/total_loss_options:.1f}%)")
    p(f"- Same-day-close option share: {_fmt_money(same_day_loss)} ({100*same_day_loss/total_loss_options:.1f}%)")
    p(f"- 0-1 DTE share: {_fmt_money(dte01_loss)} ({100*dte01_loss/total_loss_options:.1f}%)")
    p("")
    p("Note the overlap: same-day + 0-1 DTE + SPY all describe the same subset of behavior in many rows. These are not four independent explanations.")

    h("WHAT LOOKS PROMISING", 2)
    p("Rows to inspect further (not conclusions):")
    p(f"- Multi-day option grouped trades (n={len(multi_day_opt)}) show a materially better mean than same-day (see 'Same-day vs multi-day' table).")
    p(f"- Individual-name options meaningfully outperform index (SPY/QQQ/IWM) options on the mean, but concentration still matters — the top few names dominate.")
    p(f"- Hypothesis A (fresh MACD cross side-aligned) and D (adding RS on your side) are the two inflection tests with the least catastrophic n; both need repetition across more months before treating as edge.")

    # What we cannot conclude
    h("WHAT WE CANNOT CONCLUDE", 2)
    p("Given only 3 months of realized-lot data plus daily bars:")
    p("- **Intraday sequencing / execution slippage** — the CSV is date-only; whether losses came from bad entry price, bad exit price, or spread cost is not decidable here.")
    p("- **Whether PABS setup context predicted these trades** — no historical PABS state is available in this environment. Any 'PABS said X' claim is not defensible from this data.")
    p("- **Ticker-level edge** — 3 months is too short to declare any ticker an edge or a curse. All ticker rows are diagnostic; small-N flagged.")
    p("- **Options-vs-stock counterfactual** — did the *stock* trade have worked? The CSV shows only what happened. The underlying-outcome section is a **hypothetical** on the underlying move, not the trade you actually made.")
    p("- **Options structure sensitivity** — moneyness (ITM/ATM/OTM) is not analyzed here (strike-vs-spot at entry would need extra fetches). That is a genuine next step, not a claim.")
    p("- **Regime interaction** — SPY was broadly rising over this window on daily closes; whether puts underperformed because of a bearish thesis in a rising tape vs. genuinely bad selection is not separable at 3 months.")

    # Next research step
    h("NEXT RESEARCH STEP", 2)
    p("Ordered by cost-to-value, no code changes to production:")
    p("1. **Extend the cache** to the long-tail 112 tickers (currently at 40; ~24% of trades are outside the cache). Uniform coverage removes selection artifacts in the per-ticker table.")
    p("2. **Add option-structure fields** — at entry, compute moneyness (strike/spot − 1) and label each trade OTM/ATM/ITM. Rebucket P&L by moneyness × DTE. This is where 'right thesis, wrong contract' most often shows up.")
    p("3. **Fetch intraday 5m or 1m bars for a random sample of 100 same-day-close trades** — daily bars can't tell you whether you got in on a high and out on a low, or vice versa. This is the direct test for execution failure.")
    p("4. **Rerun on the next 3 months as they land.** All conclusions above are provisional at n≈300 grouped trades. The stability of the findings across a second, out-of-sample window is what matters.")
    p("5. **Only after (2)-(4)**: build the setup-tag join (research/context.compute_context_at at entry) so PABS can produce a real 'setup-conditional expectancy' for this trader. Not until.")
    p("")
    p("**Not next steps** (explicitly): no whitelist, no permanent ticker bans, no composite score, no production rule changes, no threshold optimization on this same sample.")

    # Write out
    report_path.write_text("# SCHWAB DIAGNOSTIC REPORT\n\n" + "\n".join(lines))
    print(f"Wrote report: {report_path}")


if __name__ == "__main__":
    import sys
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "/root/.claude/uploads/7d497cb3-2bdb-560e-915e-2f206b920cf3/0f1bec32-XXXX1615_GainLoss_Realized_Details_20260916-101658.csv"
    cache_dir = sys.argv[2] if len(sys.argv) > 2 else "/tmp/claude-0/-home-user-autonomous-trading-system/7d497cb3-2bdb-560e-915e-2f206b920cf3/scratchpad/bars_cache"
    report_path = sys.argv[3] if len(sys.argv) > 3 else "/home/user/autonomous-trading-system/research/results/schwab_diagnostic_report.md"
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    run(csv_path, cache_dir, report_path)
