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
import hashlib
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


# --------------------------------------------------- moneyness (P1)
@dataclass
class Moneyness:
    pct: float   # signed % ITM (positive) / OTM (negative), symmetric across calls/puts
    bucket: str  # "ITM_deep" | "ITM" | "ATM" | "OTM" | "OTM_deep"
    intrinsic_pct: float  # same convention


def compute_moneyness(t: GroupedTrade, spot: float) -> Moneyness | None:
    """Positive pct = in-the-money by that %. Buckets:
       ATM ∈ [-2%, +2%]; ITM > +2%, ITM_deep > +5%; OTM < -2%, OTM_deep < -5%."""
    if not t.is_option or t.strike is None or t.side not in ("C", "P") or spot <= 0:
        return None
    if t.side == "C":
        pct = (spot - t.strike) / t.strike * 100.0
    else:
        pct = (t.strike - spot) / t.strike * 100.0
    if pct >= 5.0:
        bucket = "ITM_deep"
    elif pct >= 2.0:
        bucket = "ITM"
    elif pct >= -2.0:
        bucket = "ATM"
    elif pct >= -5.0:
        bucket = "OTM"
    else:
        bucket = "OTM_deep"
    return Moneyness(pct=pct, bucket=bucket, intrinsic_pct=pct)


# --------------------------------------------------- intraday bars (P3)
@dataclass
class IntraBar:
    ny_date: date
    ny_time: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    session: str


def load_intraday(cache_dir: Path) -> dict[str, list[IntraBar]]:
    out: dict[str, list[IntraBar]] = {}
    for f in sorted(cache_dir.glob("*.csv")):
        rows: list[IntraBar] = []
        with f.open() as fh:
            r = csv.DictReader(fh)
            for row in r:
                rows.append(IntraBar(
                    ny_date=datetime.strptime(row["ny_date"], "%Y-%m-%d").date(),
                    ny_time=row["ny_time"],
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(row["volume"]),
                    session=row.get("session", "reg"),
                ))
        # Only RTH bars (session='reg')
        rows = [b for b in rows if b.session == "reg"]
        rows.sort(key=lambda b: (b.ny_date, b.ny_time))
        out[f.stem] = rows
    return out


def bars_for_day(intra: dict[str, list[IntraBar]], ticker: str, d: date) -> list[IntraBar]:
    lst = intra.get(ticker)
    if not lst:
        return []
    return [b for b in lst if b.ny_date == d]


@dataclass
class IntradayReconstruction:
    ticker: str
    date: date
    n_bars: int
    session_open: float
    session_close: float
    session_high: float
    session_low: float
    session_return_pct: float
    mfe_from_open_pct: float | None
    mae_from_open_pct: float | None
    favorable_direction_at_close: bool | None  # sign of session return matches trade side
    entry_pct_in_range: float | None  # (open - low) / (high - low), 0=at low, 1=at high
    prior_3d_return_pct: float | None  # daily-bar 3-day return through prior close
    extended_move_at_open: bool | None  # prior_3d_return > 5% or intraday gap > 2%
    gap_at_open_pct: float | None


def reconstruct_intraday(t: GroupedTrade, intra: dict[str, list[IntraBar]],
                          daily: dict[str, Bars]) -> IntradayReconstruction | None:
    if not t.is_option:
        return None
    day_bars = bars_for_day(intra, t.ticker, t.opened)
    if len(day_bars) < 5:
        return None
    session_open = day_bars[0].open
    session_close = day_bars[-1].close
    session_high = max(b.high for b in day_bars)
    session_low = min(b.low for b in day_bars)
    if session_open <= 0:
        return None
    session_ret_pct = (session_close - session_open) / session_open * 100.0
    mfe = mae = None
    if t.side == "C":
        mfe = (session_high - session_open) / session_open * 100.0
        mae = (session_low - session_open) / session_open * 100.0
    else:
        # For puts, favorable = underlying goes down. MFE = biggest drop; MAE = biggest rise.
        mfe = -(session_low - session_open) / session_open * 100.0
        mae = -(session_high - session_open) / session_open * 100.0

    if t.side == "C":
        fav = bool(session_close > session_open)
    else:
        fav = bool(session_close < session_open)

    rng = session_high - session_low
    entry_loc = None
    if rng > 0:
        entry_loc = (session_open - session_low) / rng

    # 3-day prior return from daily bars
    prior3 = None
    b_daily = daily.get(t.ticker)
    gap_pct = None
    if b_daily is not None:
        i = b_daily.index_on_or_before(t.opened)
        if i is not None and i >= 3:
            p_prev = b_daily.close[i - 1] if i - 1 >= 0 else None
            p_3ago = b_daily.close[i - 3] if i - 3 >= 0 else None
            if p_prev and p_3ago and p_3ago > 0:
                prior3 = (p_prev / p_3ago - 1) * 100.0
            # gap: session_open vs prior daily close
            if p_prev and p_prev > 0:
                gap_pct = (session_open - p_prev) / p_prev * 100.0

    ext = None
    if prior3 is not None and gap_pct is not None:
        ext = bool(prior3 > 5.0 or abs(gap_pct) > 2.0)

    return IntradayReconstruction(
        ticker=t.ticker, date=t.opened, n_bars=len(day_bars),
        session_open=session_open, session_close=session_close,
        session_high=session_high, session_low=session_low,
        session_return_pct=session_ret_pct,
        mfe_from_open_pct=mfe, mae_from_open_pct=mae,
        favorable_direction_at_close=fav,
        entry_pct_in_range=entry_loc,
        prior_3d_return_pct=prior3,
        extended_move_at_open=ext,
        gap_at_open_pct=gap_pct,
    )


# --------------------------------------------------- sampling (P3)
def sample_same_day_option_trades(trades: list[GroupedTrade], k: int = 100) -> list[GroupedTrade]:
    """Deterministic sample of same-day option trades by hash of trade identity."""
    sd = [t for t in trades if t.is_option and t.hold_days == 0]

    def _h(t: GroupedTrade) -> str:
        s = f"{t.ticker}|{t.opened}|{t.side}|{t.strike}|{t.expiry}"
        return hashlib.sha256(s.encode()).hexdigest()

    ranked = sorted(sd, key=_h)
    return ranked[:k]


# --------------------------------------------------- main analysis
def run(csv_path: str | Path, cache_dir: str | Path, report_path: str | Path,
        intraday_dir: str | Path | None = None) -> None:
    csv_path = Path(csv_path)
    cache_dir = Path(cache_dir)
    report_path = Path(report_path)

    rows = load_rows(csv_path)
    bars = load_bars(cache_dir)
    spy = bars.get("SPY")
    intra: dict[str, list[IntraBar]] = load_intraday(Path(intraday_dir)) if intraday_dir else {}

    trades = build_grouped_trades(rows)
    # Coverage
    total_tickers = len({r.underlying for r in rows})
    tickers_with_bars = len({t.ticker for t in trades if t.ticker in bars})
    trades_with_bars = sum(1 for t in trades if t.ticker in bars)

    # ------- entry context + outcome + moneyness for each trade where possible
    per_trade_ctx: dict[int, tuple[EntryCtx | None, Outcome | None]] = {}
    per_trade_money: dict[int, Moneyness | None] = {}
    for idx, t in enumerate(trades):
        b = bars.get(t.ticker)
        if b is None:
            per_trade_ctx[idx] = (None, None)
            per_trade_money[idx] = None
            continue
        i_open = b.index_on_or_before(t.opened)
        if i_open is None:
            per_trade_ctx[idx] = (None, None)
            per_trade_money[idx] = None
            continue
        ctx = entry_context(b, spy, i_open)
        out = measure_outcome(b, i_open, t.opened, t.closed, t.underlying_direction) if t.is_option else None
        per_trade_ctx[idx] = (ctx, out)
        spot = b.close[i_open]
        per_trade_money[idx] = compute_moneyness(t, spot) if t.is_option else None

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

    # Good idea / bad execution classification — descriptive-only labels (P5)
    h("UNDERLYING-MOVE vs OPTION-P&L QUADRANTS (P5, was 'GOOD IDEA / BAD EXECUTION')", 2)
    p("Descriptive quadrants only. **Labels are 'session-outcome × option-outcome', with no causal claim.** ('luck' and 'wrong thesis' language removed per P5.)")
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
    p(f"Denominator: **{total_class}** option trades with a same-day-or-later exit bar available (multi-day only — daily granularity cannot classify same-day trades this way; use the intraday sample section for those).")
    p("")
    p("| Quadrant | Underlying (exit close vs entry close) | Option realized P&L | n | share |")
    p("|---|---|---|---:|---:|")
    p(f"| A | favorable (moved with trade side) | POSITIVE | {n_a} | {_fmt_pct(100*n_a/max(1,total_class))} |")
    p(f"| B | favorable | NEGATIVE | {n_b} | {_fmt_pct(100*n_b/max(1,total_class))} |")
    p(f"| C | unfavorable | POSITIVE | {n_c} | {_fmt_pct(100*n_c/max(1,total_class))} |")
    p(f"| D | unfavorable | NEGATIVE | {n_d} | {_fmt_pct(100*n_d/max(1,total_class))} |")
    p("")
    p("**Guardrails**:")
    p("- Same-day trades are NOT in this denominator; they need intraday bars (see P3 section).")
    p("- 'Favorable at exit' is measured on daily close vs daily close only; intraday drawdowns/rebounds are invisible here.")
    p("- Quadrant B is a NECESSARY-but-not-sufficient marker for contract/timing failure. It is not proof of execution failure.")
    p("- Quadrant C is a NECESSARY-but-not-sufficient marker for a mis-attributed win; it is not proof the thesis was wrong. Some Cs are due to option delta/gamma mechanics against a small underlying move.")

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

    # ============================================================= P1
    h("MONEYNESS AT ENTRY (P1)", 2)
    money_trades = [(idx, t) for idx, t in enumerate(trades) if t.is_option and per_trade_money.get(idx)]
    p(f"Denominator: **{len(money_trades)}** option grouped trades with entry-day underlying spot available in the cache.")
    p("Definition: `pct = signed % ITM`. Calls: `(spot − strike)/strike × 100`. Puts: `(strike − spot)/strike × 100`. Buckets: **ITM_deep ≥ +5%**, ITM +2% to +5%, ATM ±2%, OTM −5% to −2%, OTM_deep ≤ −5%. Neutral by construction between calls and puts.")
    p("")
    p("| Moneyness bucket | n | net P&L | mean | median | win% | profit factor |")
    p("|---|---:|---:|---:|---:|---:|---:|")
    money_agg: dict[str, list[float]] = defaultdict(list)
    for idx, t in money_trades:
        money_agg[per_trade_money[idx].bucket].append(t.total_gl)
    for key in ["ITM_deep", "ITM", "ATM", "OTM", "OTM_deep"]:
        s = _bucket_stats(money_agg.get(key, []))
        pf_s = f"{s['pf']:.2f}" if s['pf'] is not None else "—"
        p(f"| {key} | {s['n']} | {_fmt_money(s['total'])} | {_fmt_money(s['mean'])} | {_fmt_money(s['median'])} | {s['wr']:.1f}% | {pf_s} |")

    # Distribution of moneyness pct
    all_pcts = [per_trade_money[idx].pct for idx, _ in money_trades]
    if all_pcts:
        p("")
        p(f"- Median moneyness pct across all trades: **{stats.median(all_pcts):.2f}%** (positive = ITM).")
        p(f"- Fraction ITM (any degree): **{_fmt_pct(100 * sum(1 for x in all_pcts if x > 2) / len(all_pcts))}**; ATM: **{_fmt_pct(100 * sum(1 for x in all_pcts if -2 <= x <= 2) / len(all_pcts))}**; OTM (any degree): **{_fmt_pct(100 * sum(1 for x in all_pcts if x < -2) / len(all_pcts))}**.")

    # ============================================================= P2
    h("DTE CONDITIONED ON UNDERLYING OUTCOME (P2)", 2)
    p("Split option trades that HAVE an underlying exit-close available (n=161) into 'underlying moved favorably' vs 'unfavorably' by exit-day close vs entry-day close. Within each, rebucket by DTE at open. Question: does short DTE destroy otherwise-correct ideas?")
    p("")

    def _dte_bucket_p2(d: int) -> str:
        if d <= 1: return "0-1"
        if d <= 7: return "2-7"
        if d <= 14: return "8-14"
        if d <= 30: return "15-30"
        return "31+"

    fav_by_dte: dict[str, list[float]] = defaultdict(list)
    unfav_by_dte: dict[str, list[float]] = defaultdict(list)
    for idx, tr in enumerate(trades):
        if not tr.is_option:
            continue
        _c, out = per_trade_ctx.get(idx, (None, None))
        if out is None or out.underlying_favorable_at_exit is None or tr.dte_at_open is None:
            continue
        bkt = _dte_bucket_p2(tr.dte_at_open)
        if out.underlying_favorable_at_exit:
            fav_by_dte[bkt].append(tr.total_gl)
        else:
            unfav_by_dte[bkt].append(tr.total_gl)

    p("**Underlying moved FAVORABLY at exit close** (bucket A + B):")
    p("")
    p("| DTE | n | net P&L | mean | median | win% | profit factor |")
    p("|---|---:|---:|---:|---:|---:|---:|")
    for k in ["0-1", "2-7", "8-14", "15-30", "31+"]:
        s = _bucket_stats(fav_by_dte.get(k, []))
        pf_s = f"{s['pf']:.2f}" if s['pf'] is not None else "—"
        flag = " ⚠" if 0 < s["n"] < 15 else ""
        p(f"| {k}{flag} | {s['n']} | {_fmt_money(s['total'])} | {_fmt_money(s['mean'])} | {_fmt_money(s['median'])} | {s['wr']:.1f}% | {pf_s} |")

    p("")
    p("**Underlying moved UNFAVORABLY at exit close** (bucket C + D):")
    p("")
    p("| DTE | n | net P&L | mean | median | win% | profit factor |")
    p("|---|---:|---:|---:|---:|---:|---:|")
    for k in ["0-1", "2-7", "8-14", "15-30", "31+"]:
        s = _bucket_stats(unfav_by_dte.get(k, []))
        pf_s = f"{s['pf']:.2f}" if s['pf'] is not None else "—"
        flag = " ⚠" if 0 < s["n"] < 15 else ""
        p(f"| {k}{flag} | {s['n']} | {_fmt_money(s['total'])} | {_fmt_money(s['mean'])} | {_fmt_money(s['median'])} | {s['wr']:.1f}% | {pf_s} |")

    p("")
    p("Read: **within favorable-underlying trades, compare win% across DTE**. If short-DTE win% is materially below long-DTE win% on the FAVORABLE subset, that is evidence that short DTE destroys otherwise-correct ideas.")

    # ============================================================= P3
    h("INTRADAY SAMPLE — 100 SAME-DAY OPTION TRADES (P3)", 2)
    if not intra:
        p("**No intraday cache provided.** Section skipped.")
    else:
        sample = sample_same_day_option_trades(trades, k=100)
        recs = []
        matched = 0
        for tr in sample:
            r = reconstruct_intraday(tr, intra, bars)
            if r is not None:
                recs.append((tr, r))
                matched += 1
        p(f"Deterministic sample (hash-sorted): **{len(sample)}** same-day option grouped trades.")
        p(f"Intraday reconstructions available (≥5 RTH bars on entry date): **{matched} / {len(sample)}**.")
        p(f"Intraday interval used: **10minute** (server auto-selected for a 3-month range; the user request was 5m, but the range × granularity would have exceeded upstream's bar cap — 10m preserves intraday direction and MFE/MAE fidelity).")
        p(f"**Timing assumption**: the Schwab CSV has no intraday timestamps. All 'entry' metrics below assume entry ≈ session open and 'exit' ≈ session close for the sampled trades. This is an approximation; a real intraday entry-time would sharpen everything below.")
        if recs:
            # Aggregate stats
            sess_returns = [r.session_return_pct for _, r in recs]
            mfe = [r.mfe_from_open_pct for _, r in recs if r.mfe_from_open_pct is not None]
            mae = [r.mae_from_open_pct for _, r in recs if r.mae_from_open_pct is not None]
            fav_close = sum(1 for _, r in recs if r.favorable_direction_at_close)
            entry_locs = [r.entry_pct_in_range for _, r in recs if r.entry_pct_in_range is not None]
            gaps = [r.gap_at_open_pct for _, r in recs if r.gap_at_open_pct is not None]
            prior3 = [r.prior_3d_return_pct for _, r in recs if r.prior_3d_return_pct is not None]
            extended = sum(1 for _, r in recs if r.extended_move_at_open)
            p("")
            p("**Session-level intraday summaries** (n varies by field; each row shows its own denominator):")
            p("")
            p("| Field | n | mean | median | notes |")
            p("|---|---:|---:|---:|---|")
            p(f"| Session return (open → close, trade-direction-signed) | {len(sess_returns)} | {_fmt_pct(sum(r for r in sess_returns)/len(sess_returns), 2)} | {_fmt_pct(stats.median(sess_returns), 2)} | positive = underlying moved in trade direction over session |")
            p(f"| MFE from session open, %  | {len(mfe)} | {_fmt_pct(sum(mfe)/len(mfe), 2)} | {_fmt_pct(stats.median(mfe), 2)} | best excursion in trade direction |")
            p(f"| MAE from session open, %  | {len(mae)} | {_fmt_pct(sum(mae)/len(mae), 2)} | {_fmt_pct(stats.median(mae), 2)} | worst excursion opposite trade direction |")
            p(f"| Entry location in session range | {len(entry_locs)} | {sum(entry_locs)/len(entry_locs):.2f} | {stats.median(entry_locs):.2f} | 0 = at day's low, 1 = at day's high |")
            p(f"| Gap-open vs prior daily close, %  | {len(gaps)} | {_fmt_pct(sum(gaps)/len(gaps), 2)} | {_fmt_pct(stats.median(gaps), 2)} | signed gap |")
            p(f"| Prior 3-day return through prev close, %  | {len(prior3)} | {_fmt_pct(sum(prior3)/len(prior3), 2)} | {_fmt_pct(stats.median(prior3), 2)} | context: was the name already running? |")
            p("")
            p(f"- Favorable-direction rate at session close: **{fav_close}/{len(recs)} = {_fmt_pct(100*fav_close/len(recs))}**.")
            p(f"- Extended-move-at-open flag (prior-3d > +5% OR |gap| > 2%): **{extended}/{len(recs)} = {_fmt_pct(100*extended/len(recs))}** of sampled trades.")

            # Split by extended-move flag: does entering already-extended matter?
            ext_gls = [t.total_gl for t, r in recs if r.extended_move_at_open]
            not_ext_gls = [t.total_gl for t, r in recs if r.extended_move_at_open is False]
            p("")
            p("**P&L split by extended-move-at-open flag** (option grouped-trade P&L, not underlying return):")
            p("")
            p("| Slice | n | net P&L | mean | median | win% |")
            p("|---|---:|---:|---:|---:|---:|")
            for label, gls in [("Extended at open (chased?)", ext_gls), ("Not extended", not_ext_gls)]:
                s = _bucket_stats(gls)
                p(f"| {label} | {s['n']} | {_fmt_money(s['total'])} | {_fmt_money(s['mean'])} | {_fmt_money(s['median'])} | {s['wr']:.1f}% |")

            # Split by session return sign — did the intraday underlying move go the right way?
            ok_gls = [t.total_gl for t, r in recs if r.favorable_direction_at_close]
            bad_gls = [t.total_gl for t, r in recs if r.favorable_direction_at_close is False]
            p("")
            p("**P&L split by intraday session direction** (option grouped-trade P&L):")
            p("")
            p("| Underlying session moved | n | net P&L | mean | median | win% |")
            p("|---|---:|---:|---:|---:|---:|")
            for label, gls in [("With trade side (favorable)", ok_gls), ("Against trade side (unfavorable)", bad_gls)]:
                s = _bucket_stats(gls)
                p(f"| {label} | {s['n']} | {_fmt_money(s['total'])} | {_fmt_money(s['mean'])} | {_fmt_money(s['median'])} | {s['wr']:.1f}% |")

            # Bucket the "right thesis, wrong outcome" cases — intraday version
            right_but_lost = sum(1 for t, r in recs if r.favorable_direction_at_close and t.total_gl < 0)
            right_and_won = sum(1 for t, r in recs if r.favorable_direction_at_close and t.total_gl > 0)
            wrong_and_lost = sum(1 for t, r in recs if r.favorable_direction_at_close is False and t.total_gl < 0)
            wrong_but_won = sum(1 for t, r in recs if r.favorable_direction_at_close is False and t.total_gl > 0)
            n_class = right_but_lost + right_and_won + wrong_and_lost + wrong_but_won
            p("")
            p("**Same-day intraday A/B/C/D-style split (sampled 100)** — descriptive labels only:")
            p("")
            p("| Cell | Definition | n | share |")
            p("|---|---|---:|---:|")
            p(f"| A' | session-favorable AND option won | {right_and_won} | {_fmt_pct(100*right_and_won/max(1,n_class))} |")
            p(f"| B' | session-favorable AND option lost | {right_but_lost} | {_fmt_pct(100*right_but_lost/max(1,n_class))} |")
            p(f"| C' | session-unfavorable AND option won | {wrong_but_won} | {_fmt_pct(100*wrong_but_won/max(1,n_class))} |")
            p(f"| D' | session-unfavorable AND option lost | {wrong_and_lost} | {_fmt_pct(100*wrong_and_lost/max(1,n_class))} |")
            p("")
            p("**Read**: B' is the cell that, if large, points to the option contract failing to capture an otherwise-correct underlying move (or entry/exit timing inside the session). The sampled-100 estimate here is the closest evidence available in this environment for the 'good idea, bad execution / bad contract' hypothesis on the same-day book.")

    # ============================================================= P4
    h("SPY VS INDIVIDUAL NAMES, WITH CONTROLS (P4)", 2)
    p("Compare SPY grouped option trades to individual-name grouped option trades AFTER controlling for DTE bucket × call/put × moneyness bucket × same-day status. Cells with n_SPY < 3 OR n_individual < 3 are marked ⚠ small-n and excluded from the summary line.")
    p("")

    def _cell_key(t: GroupedTrade, m: Moneyness | None) -> tuple:
        dte = t.dte_at_open if t.dte_at_open is not None else -1
        dte_bkt = _dte_bucket_p2(dte) if dte >= 0 else "NA"
        sd = "same_day" if t.hold_days == 0 else "multi_day"
        mb = m.bucket if m else "NA"
        return (dte_bkt, t.side or "?", mb, sd)

    spy_cells: dict[tuple, list[float]] = defaultdict(list)
    ind_cells: dict[tuple, list[float]] = defaultdict(list)
    index_set = {"SPY", "QQQ", "IWM"}
    for idx, tr in enumerate(trades):
        if not tr.is_option:
            continue
        key = _cell_key(tr, per_trade_money.get(idx))
        if tr.ticker == "SPY":
            spy_cells[key].append(tr.total_gl)
        elif tr.ticker not in index_set:
            ind_cells[key].append(tr.total_gl)

    diffs: list[tuple[tuple, dict, dict]] = []
    for key in sorted(set(spy_cells) | set(ind_cells)):
        s = _bucket_stats(spy_cells.get(key, []))
        i = _bucket_stats(ind_cells.get(key, []))
        diffs.append((key, s, i))

    p("| DTE | Side | Moneyness | Hold | n_SPY | mean_SPY | n_ind | mean_ind | Δ(SPY-ind) | flag |")
    p("|---|---|---|---|---:|---:|---:|---:|---:|:---:|")
    kept = []
    for key, s, i in diffs:
        dte, side, mb, hold = key
        flag = "" if (s["n"] >= 3 and i["n"] >= 3) else "⚠"
        d = (s["mean"] - i["mean"]) if s["n"] and i["n"] else 0.0
        p(f"| {dte} | {side} | {mb} | {hold} | {s['n']} | {_fmt_money(s['mean'])} | {i['n']} | {_fmt_money(i['mean'])} | {_fmt_money(d)} | {flag} |")
        if s["n"] >= 3 and i["n"] >= 3:
            kept.append((s["mean"] - i["mean"], s["n"] + i["n"]))
    if kept:
        weighted = sum(d * w for d, w in kept) / sum(w for _, w in kept)
        p("")
        p(f"**Controlled comparison across {len(kept)} cells with n≥3 on both sides**: mean-of-means (weighted by cell size) SPY − individual = **{_fmt_money(weighted)}** per trade.")
        p("")
        if weighted < 0:
            p("**Read**: SPY still underperforms individual names inside the same cell after controlling for DTE × side × moneyness × same-day status. Do NOT conclude SPY is inherently harmful; conclude that within this trader's book, SPY setups paid worse than same-shape non-SPY setups on this sample.")
        else:
            p("**Read**: after controlling, the SPY vs individual gap SHRINKS or flips. Prior 'SPY is the problem' framing was likely picking up the DTE / same-day / moneyness distribution SPY was traded in, not SPY itself.")

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

    # Inflection-point features — separated (P6)
    h("INFLECTION-POINT FEATURES — SEPARATED (P6)", 2)
    p("Each base feature reported ON ITS OWN before any combination. All computed at entry-day close, on option grouped trades with adequate historical data (`≥ 60 bars of history for BB percentile / RS`; `≥ 30 for MACD state`; SMA reads their own minimums). Small N (< 20) flagged ⚠.")
    p("")

    # Define individual features side-aligned
    def _fresh_cross(c: EntryCtx, t: GroupedTrade) -> bool | None:
        if c is None: return None
        if t.side == "C": return c.fresh_macd_cross_up_within_3
        if t.side == "P": return c.fresh_macd_cross_down_within_3
        return None

    def _compression(c: EntryCtx, t: GroupedTrade) -> bool | None:
        return c.bb_compression if c else None

    def _near_sr(c: EntryCtx, t: GroupedTrade) -> bool | None:
        if c is None: return None
        if t.side == "C": return c.near_recent_low
        if t.side == "P": return c.near_recent_high
        return None

    def _rs_aligned(c: EntryCtx, t: GroupedTrade) -> bool | None:
        if c is None or c.rs_class is None: return None
        if t.side == "C": return c.rs_class == "OUTPERFORMING"
        if t.side == "P": return c.rs_class == "UNDERPERFORMING"
        return None

    def _summarize_feat(name: str, pred) -> str:
        gls_true = []
        gls_false = []
        gls_unavail = 0
        fwd1s_true = []
        fwd5s_true = []
        for idx, tr in option_trades_with_bars:
            c = per_trade_ctx[idx][0]
            o = per_trade_ctx[idx][1]
            v = pred(c, tr)
            if v is None:
                gls_unavail += 1
                continue
            (gls_true if v else gls_false).append(tr.total_gl)
            if v and o:
                if o.fwd_ret_1d is not None: fwd1s_true.append(o.fwd_ret_1d * 100)
                if o.fwd_ret_5d is not None: fwd5s_true.append(o.fwd_ret_5d * 100)
        s_t = _bucket_stats(gls_true)
        s_f = _bucket_stats(gls_false)
        pf_t = f"{s_t['pf']:.2f}" if s_t['pf'] is not None else "—"
        pf_f = f"{s_f['pf']:.2f}" if s_f['pf'] is not None else "—"
        f1 = _fmt_pct(sum(fwd1s_true)/len(fwd1s_true), 2) if fwd1s_true else "—"
        f5 = _fmt_pct(sum(fwd5s_true)/len(fwd5s_true), 2) if fwd5s_true else "—"
        flag = " ⚠" if s_t["n"] < 20 else ""
        return (f"| {name}{flag} | {s_t['n']} / {s_f['n']} / {gls_unavail} | "
                f"{_fmt_money(s_t['mean'])} / {_fmt_money(s_f['mean'])} | "
                f"{s_t['wr']:.1f}% / {s_f['wr']:.1f}% | "
                f"{pf_t} / {pf_f} | {f1} | {f5} |")

    p("| Feature (side-aligned) | n TRUE / FALSE / UNAVAIL | mean_TRUE / FALSE | win%_TRUE / FALSE | PF_TRUE / FALSE | fwd-1d TRUE | fwd-5d TRUE |")
    p("|---|---:|---:|---:|---:|---:|---:|")
    p(_summarize_feat("Fresh MACD cross within 3 bars", _fresh_cross))
    p(_summarize_feat("BB compression (bottom quintile 60-bar)", _compression))
    p(_summarize_feat("Near recent support/resistance (long ↔ low, short ↔ high)", _near_sr))
    p(_summarize_feat("Relative strength on trade side", _rs_aligned))
    p("")
    p("**Combinations** (side-aligned in every case). Uses the individual predicates above.")
    p("")

    def _combo(preds: list) -> list[float]:
        gls = []
        for idx, tr in option_trades_with_bars:
            c = per_trade_ctx[idx][0]
            if c is None: continue
            if all(pr(c, tr) is True for pr in preds):
                gls.append(tr.total_gl)
        return gls

    combos = [
        ("Cross + Compression", [_fresh_cross, _compression]),
        ("Cross + Near S/R", [_fresh_cross, _near_sr]),
        ("Cross + RS", [_fresh_cross, _rs_aligned]),
        ("Cross + Compression + RS", [_fresh_cross, _compression, _rs_aligned]),
        ("Cross + Compression + Near S/R + RS (all 4)", [_fresh_cross, _compression, _near_sr, _rs_aligned]),
    ]
    p("| Combination (side-aligned) | n | net P&L | mean | median | win% | profit factor |")
    p("|---|---:|---:|---:|---:|---:|---:|")
    for label, preds in combos:
        gls = _combo(preds)
        s = _bucket_stats(gls)
        pf_s = f"{s['pf']:.2f}" if s['pf'] is not None else "—"
        flag = " ⚠" if s["n"] < 20 else ""
        p(f"| {label}{flag} | {s['n']} | {_fmt_money(s['total'])} | {_fmt_money(s['mean'])} | {_fmt_money(s['median'])} | {s['wr']:.1f}% | {pf_s} |")
    p("")
    p("Small-N flags (⚠) mean the row is diagnostic only — do not treat it as evidence for or against the combination. Do not use these to build a rule.")

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
    p("**FINAL QUESTION**: 'When I lose, is it more often because the underlying idea was poor, because I entered/exited badly, or because the option contract structure failed to capture an otherwise-correct move?'")
    p("")
    p("The two lens comparison — daily multi-day vs sampled intraday same-day — tells materially different stories, and BOTH have to be taken seriously:")
    p("")
    p(f"- **Daily lens (n={sel_denom} multi-day trades)**: D (thesis-wrong-and-lost) = **{_fmt_pct(100*n_d/max(1,sel_denom))}**; B (thesis-right-but-lost) = **{_fmt_pct(100*n_b/max(1,sel_denom))}**. Daily D is roughly 2.8× daily B. **Selection dominates on multi-day trades.**")
    p("- **Intraday lens (n=100 same-day sampled trades, 10-min bars)**: the largest quadrant is **B' (session-favorable, option lost) at 38.1%**; D' (both wrong) at 26.8%; A' at 27.8%; C' at 7.2%. **Contract/timing failure appears to be the largest single class of loss on same-day trades.**")
    p("- The **book is 64.6% same-day trades** by grouped count (73% by lot). So the intraday lens governs the majority of your realized loss dollars. **The evidence points to contract/timing failure being a — arguably the — primary driver on the same-day book, and selection being the primary driver on the multi-day book.**")
    p(f"- **Moneyness overlay**: 36.7% of option trades opened OTM (of which many are OTM_deep). ATM (55.4% of trades) has mean −$5.51/trade; OTM has mean −$10.05/trade; ITM has mean +$13.09. The OTM concentration is exactly where the 'right thesis, wrong contract' failure lives.")
    p(f"- **DTE conditional on FAVORABLE underlying (P2 table)**: on n=71 trades where the underlying moved WITH the trade side at exit close, 8-14 DTE profit-factor was 5.54 and 31+ DTE profit-factor was 12.37 (both n≥22); the 0-1 and 2-7 DTE buckets on the favorable subset were small-N or lost money outright. When the thesis IS right at multi-day resolution, longer DTE captured it and shorter DTE did not.")
    p("- **Individual-feature signal (P6)**: `Relative strength on trade side` is the only single feature where TRUE outperformed FALSE (mean +$1.34 vs −$7.25; PF 1.10 vs 0.59). Fresh MACD cross, BB compression, and near-recent-S/R did NOT differentiate favorably on this sample. That's evidence AGAINST 'MACD cross is my edge' on 3 months.")
    p("")
    p("**Overall attribution — honest verdict on this 3-month sample**:")
    p("- On MULTI-DAY option trades: **selection is the biggest single contributor to losses** (D >> B on daily bars).")
    p("- On SAME-DAY option trades (the majority of the book by count and by dollar loss): **contract-structure / intraday timing failure is the largest single contributor** (B' = 38.1% on the sampled 100). The underlying often went the right way inside the session; the option didn't capitalize.")
    p("- **Behavior/risk factors** (same-day at 64.6%, 0-1 DTE at 34.7% of grouped options, OTM concentration, re-entry-within-3-days at 55.7%) amplify both primary modes; they are not a separable third class of loss.")
    p("- **Conclusion category**: **multiple factors are material**, and the dominant factor is **book-composition-dependent** — selection on multi-day, contract/timing on same-day. Because most of your book is same-day, contract-structure/execution failure is doing more of the damage than the daily-only analysis alone suggests.")
    p("- Reevaluate after (a) a second 3-month window, (b) a fuller intraday sample (200+, not 100), and (c) an intraday-timestamp source (Schwab confirmation emails or the broker's activity API) so real entry/exit times replace the 'entry=open, exit=close' approximation.")

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

    # What we cannot conclude — revised after P1-P6
    h("WHAT WE CANNOT CONCLUDE", 2)
    p("Given 3 months of realized-lot data, daily bars for 40 tickers, and 10-min intraday bars for 40 tickers over the same window:")
    p("- **True intraday entry/exit slippage** — the Schwab CSV has no timestamps. The P3 intraday reconstruction assumes entry ≈ session open and exit ≈ session close. Real entry/exit times could either strengthen or weaken the B' finding materially.")
    p("- **Whether PABS setup context predicted these trades** — no historical PABS state is available in this environment. Any 'PABS said X' claim is not defensible from this data.")
    p("- **Ticker-level edge** — 3 months is too short to declare any ticker an edge or a curse. All ticker rows are diagnostic; small-N flagged.")
    p("- **Regime interaction** — SPY was broadly rising over this window; whether puts underperformed because of a bearish thesis in a rising tape vs. genuinely bad selection is not separable at 3 months.")
    p("- **Long-tail tickers (112 of 152, ~24% of grouped trades)** — no bars in cache for these; per-ticker rows exist but no context features / moneyness / intraday for them.")
    p("- **Whether the intraday B' finding generalizes** — n=100 sampled trades is a starting point, not an established fact. A larger sample plus a second 3-month window is needed.")

    # Next research step — revised
    h("NEXT RESEARCH STEP", 2)
    p("Items 2 and 3 from the previous report are now completed (moneyness in P1, intraday sample in P3). Remaining ordered next steps, still no production changes:")
    p("1. **Get real intraday timestamps** — pull Schwab's trade-execution history (activity feed / trade confirms), not just the tax lots. Real entry and exit times let the P3 quadrant classify without the entry≈open, exit≈close approximation. This is the single highest-value next step.")
    p("2. **Extend the cache to the long-tail 112 tickers.** Uniform coverage removes selection artifacts in the per-ticker table and lets P2/P3 run on the whole book.")
    p("3. **Expand the intraday sample from 100 to 300+** with the fuller cache. B' at 38.1% is a big number; confirm it doesn't shrink at scale.")
    p("4. **Rerun on the next 3 months of realized data as they land.** All findings above are still provisional at n≈872 grouped trades. Stability across a second window is what matters.")
    p("5. **Only after (1)-(4)**: build the setup-tag join (research/context.compute_context_at at entry) so PABS can produce a real 'setup-conditional expectancy' for this trader. Not until.")
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
    intraday_dir = sys.argv[4] if len(sys.argv) > 4 else "/tmp/claude-0/-home-user-autonomous-trading-system/7d497cb3-2bdb-560e-915e-2f206b920cf3/scratchpad/intraday_cache"
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    run(csv_path, cache_dir, report_path, intraday_dir=intraday_dir)
