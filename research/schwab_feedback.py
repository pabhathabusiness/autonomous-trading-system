"""Schwab realized-gain/loss ingestor + aggregator.

Feeds the PLAYBOOK.md feedback loop: read a Schwab CSV export, produce
descriptive stats and per-ticker / DTE / hold-period breakdowns so the
playbook's whitelist / blacklist / setup gates stay tied to real numbers
instead of feelings.

CLI:
    python -m research.schwab_feedback <path/to/schwab_gainloss.csv>

Library:
    from research.schwab_feedback import load_rows, summarize, per_ticker,
        by_days_held, by_dte, wash_sale_report

Follow-up (not implemented in this pass): join each closed lot to
`research.context.compute_context_at(underlying, spy, t_open)` so PABS can
answer which setup contexts historically paid for THIS trader.
"""

from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Iterable


# ------------------------------------------------------------- parsers
_MONEY_RE = re.compile(r"^-?\$?\(?-?\$?([\d,]+(?:\.\d+)?)\)?$")
_PCT_RE = re.compile(r"^-?([\d,]+(?:\.\d+)?)%?$")
_OPT_RE = re.compile(r"^([A-Z]+)\s+(\d{2}/\d{2}/\d{4})\s+([\d.]+)\s+([CP])$")


def _parse_money(s: str) -> float | None:
    s = (s or "").strip()
    if not s or s in {"-", "—"}:
        return None
    neg = "(" in s or s.startswith("-")
    m = _MONEY_RE.match(s.replace("(", "").replace(")", ""))
    if not m:
        return None
    v = float(m.group(1).replace(",", ""))
    return -v if neg else v


def _parse_pct(s: str) -> float | None:
    s = (s or "").strip()
    if not s or s in {"-", "—"}:
        return None
    neg = s.startswith("-")
    m = _PCT_RE.match(s.replace("-", ""))
    if not m:
        return None
    v = float(m.group(1).replace(",", ""))
    return -v if neg else v


def _parse_date(s: str) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%m/%d/%Y")
    except ValueError:
        return None


# ------------------------------------------------------------- row model
@dataclass(frozen=True)
class Row:
    symbol_raw: str
    underlying: str
    is_option: bool
    option_expiry: datetime | None
    option_strike: float | None
    option_side: str | None  # "C" | "P" | None
    opened: datetime | None
    closed: datetime | None
    quantity: float
    proceeds_ps: float | None
    cost_ps: float | None
    proceeds: float | None
    cost: float | None
    gl_dollar: float | None
    gl_pct: float | None
    wash_sale: bool
    disallowed_loss: float | None

    @property
    def days_held(self) -> int | None:
        if self.opened and self.closed:
            return (self.closed - self.opened).days
        return None

    @property
    def dte_at_open(self) -> int | None:
        if self.is_option and self.opened and self.option_expiry:
            return (self.option_expiry - self.opened).days
        return None


def load_rows(csv_path: str | Path) -> list[Row]:
    """Parse a Schwab realized-gain/loss lot-detail CSV export.

    Schwab wraps the header row in the second CSV line and prefixes it with
    a title line. We skip until we see a line whose first column is "Symbol".
    """
    rows: list[Row] = []
    with Path(csv_path).open("r", encoding="utf-8", errors="replace") as fh:
        reader = csv.reader(fh)
        idx: dict[str, int] = {}
        header_seen = False
        for line in reader:
            if not line:
                continue
            if not header_seen:
                if line[0].strip() == "Symbol":
                    idx = {h.strip(): i for i, h in enumerate(line)}
                    header_seen = True
                continue

            def cell(name: str) -> str:
                i = idx.get(name)
                return line[i].strip() if i is not None and i < len(line) else ""

            sym = cell("Symbol")
            if not sym:
                continue
            m = _OPT_RE.match(sym)
            if m:
                underlying = m.group(1)
                is_opt = True
                exp = _parse_date(m.group(2))
                strike = float(m.group(3))
                side = m.group(4)
            else:
                underlying = sym.split()[0]
                is_opt = False
                exp = None
                strike = None
                side = None

            rows.append(Row(
                symbol_raw=sym,
                underlying=underlying,
                is_option=is_opt,
                option_expiry=exp,
                option_strike=strike,
                option_side=side,
                opened=_parse_date(cell("Opened Date")),
                closed=_parse_date(cell("Closed Date")),
                quantity=float((cell("Quantity") or "0").replace(",", "")),
                proceeds_ps=_parse_money(cell("Proceeds Per Share")),
                cost_ps=_parse_money(cell("Cost Per Share")),
                proceeds=_parse_money(cell("Proceeds")),
                cost=_parse_money(cell("Cost Basis (CB)")),
                gl_dollar=_parse_money(cell("Gain/Loss ($)")),
                gl_pct=_parse_pct(cell("Gain/Loss (%)")),
                wash_sale=(cell("Wash Sale?") or "").lower() == "yes",
                disallowed_loss=_parse_money(cell("Disallowed Loss")),
            ))
    return rows


# ------------------------------------------------------------- aggregators
def summarize(rows: Iterable[Row], label: str = "closed lots") -> dict:
    rows = [r for r in rows if r.gl_dollar is not None]
    if not rows:
        return {"label": label, "n": 0}
    gls = [r.gl_dollar for r in rows]
    wins = [g for g in gls if g > 0]
    losses = [g for g in gls if g < 0]
    zeros = [g for g in gls if g == 0]
    pct_wins = [r.gl_pct for r in rows if r.gl_pct is not None and r.gl_pct > 0]
    pct_losses = [r.gl_pct for r in rows if r.gl_pct is not None and r.gl_pct < 0]
    n = len(gls)
    avg_win = mean(wins) if wins else 0.0
    avg_loss = mean(losses) if losses else 0.0
    return {
        "label": label,
        "n": n,
        "n_win": len(wins), "n_loss": len(losses), "n_zero": len(zeros),
        "win_rate_pct": len(wins) / n * 100.0,
        "total_pnl": sum(gls),
        "avg_win": avg_win, "median_win": median(wins) if wins else 0.0,
        "avg_loss": avg_loss, "median_loss": median(losses) if losses else 0.0,
        "payoff": (avg_win / abs(avg_loss)) if losses else float("inf"),
        "expectancy_per_lot": ((len(wins) * avg_win) + (len(losses) * avg_loss)) / n if n else 0.0,
        "avg_win_pct": mean(pct_wins) if pct_wins else 0.0,
        "avg_loss_pct": mean(pct_losses) if pct_losses else 0.0,
    }


def per_ticker(rows: Iterable[Row]) -> list[dict]:
    """Aggregate by underlying, sorted by net P&L descending."""
    per: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        if r.gl_dollar is None:
            continue
        per[r.underlying].append(r.gl_dollar)
    out = []
    for tkr, gs in per.items():
        wins = sum(1 for g in gs if g > 0)
        out.append({
            "ticker": tkr,
            "n": len(gs),
            "total_pnl": sum(gs),
            "avg_pnl": sum(gs) / len(gs),
            "win_rate_pct": 100.0 * wins / len(gs),
        })
    return sorted(out, key=lambda d: d["total_pnl"], reverse=True)


def by_days_held(rows: Iterable[Row], *, is_option: bool | None = None) -> list[dict]:
    buckets = ["0 (intraday)", "1", "2-3", "4-7", "8-14", "15-30", "31+"]
    agg: dict[str, list[float]] = {b: [] for b in buckets}

    def _bucket(d: int) -> str:
        if d == 0: return "0 (intraday)"
        if d == 1: return "1"
        if d <= 3: return "2-3"
        if d <= 7: return "4-7"
        if d <= 14: return "8-14"
        if d <= 30: return "15-30"
        return "31+"

    for r in rows:
        if r.gl_dollar is None or r.days_held is None:
            continue
        if is_option is not None and r.is_option != is_option:
            continue
        agg[_bucket(r.days_held)].append(r.gl_dollar)
    return [_bucket_stats(b, agg[b]) for b in buckets]


def by_dte(rows: Iterable[Row]) -> list[dict]:
    buckets = ["0DTE", "1DTE", "2-5DTE", "6-14DTE", "15-30DTE", "31-60DTE", "60+DTE"]
    agg: dict[str, list[float]] = {b: [] for b in buckets}

    def _bucket(d: int) -> str:
        if d == 0: return "0DTE"
        if d == 1: return "1DTE"
        if d <= 5: return "2-5DTE"
        if d <= 14: return "6-14DTE"
        if d <= 30: return "15-30DTE"
        if d <= 60: return "31-60DTE"
        return "60+DTE"

    for r in rows:
        if not r.is_option or r.gl_dollar is None or r.dte_at_open is None:
            continue
        agg[_bucket(r.dte_at_open)].append(r.gl_dollar)
    return [_bucket_stats(b, agg[b]) for b in buckets]


def _bucket_stats(name: str, gs: list[float]) -> dict:
    if not gs:
        return {"bucket": name, "n": 0, "total_pnl": 0.0, "avg_pnl": 0.0, "win_rate_pct": 0.0}
    wins = sum(1 for g in gs if g > 0)
    return {
        "bucket": name,
        "n": len(gs),
        "total_pnl": sum(gs),
        "avg_pnl": sum(gs) / len(gs),
        "win_rate_pct": 100.0 * wins / len(gs),
    }


def wash_sale_report(rows: Iterable[Row]) -> dict:
    ws = [r for r in rows if r.wash_sale]
    disallowed = sum(r.disallowed_loss for r in ws if r.disallowed_loss is not None)
    return {"n_lots_flagged": len(ws), "disallowed_loss_total": disallowed}


def biggest(rows: Iterable[Row], k: int = 10) -> tuple[list[Row], list[Row]]:
    gl = [r for r in rows if r.gl_dollar is not None]
    top = sorted(gl, key=lambda r: r.gl_dollar or 0)[-k:][::-1]
    bot = sorted(gl, key=lambda r: r.gl_dollar or 0)[:k]
    return top, bot


# ------------------------------------------------------------- CLI printer
def _fmt(rows: list[Row]) -> str:
    equity = [r for r in rows if not r.is_option]
    options = [r for r in rows if r.is_option]

    def _summary_lines(label: str, s: dict) -> list[str]:
        if s.get("n", 0) == 0:
            return [f"=== {label} === (n=0)"]
        return [
            f"=== {label} ===",
            f"  n_closed_lots  = {s['n']}",
            f"  W / L / 0      = {s['n_win']} / {s['n_loss']} / {s['n_zero']}",
            f"  win_rate       = {s['win_rate_pct']:.1f}%",
            f"  total_P&L      = ${s['total_pnl']:,.2f}",
            f"  avg_win        = ${s['avg_win']:,.2f}  (median ${s['median_win']:,.2f})",
            f"  avg_loss       = ${s['avg_loss']:,.2f}  (median ${s['median_loss']:,.2f})",
            f"  payoff         = {s['payoff']:.2f}x",
            f"  expectancy/lot = ${s['expectancy_per_lot']:,.2f}",
        ]

    lines: list[str] = []
    lines.append(f"Rows: {len(rows)}   equity: {len(equity)}   options: {len(options)}")
    lines.append("")
    lines.extend(_summary_lines("ALL closed lots", summarize(rows, "all")))
    lines.append("")
    lines.extend(_summary_lines("EQUITY closed lots", summarize(equity, "equity")))
    lines.append("")
    lines.extend(_summary_lines("OPTION closed lots", summarize(options, "options")))
    lines.append("")
    ws = wash_sale_report(rows)
    lines.append(f"=== Wash sales === lots={ws['n_lots_flagged']}   disallowed_loss=${ws['disallowed_loss_total']:,.2f}")
    lines.append("")
    lines.append("=== Options — P&L by days-to-expiry at open ===")
    lines.append(f"  {'BUCKET':<12} {'N':>4} {'TOTAL':>12} {'AVG':>10} {'WIN%':>6}")
    for b in by_dte(rows):
        lines.append(f"  {b['bucket']:<12} {b['n']:>4} ${b['total_pnl']:>10,.2f} ${b['avg_pnl']:>8,.2f} {b['win_rate_pct']:>5.1f}%")
    lines.append("")
    lines.append("=== Options — P&L by holding period ===")
    lines.append(f"  {'BUCKET':<14} {'N':>4} {'TOTAL':>12} {'AVG':>10} {'WIN%':>6}")
    for b in by_days_held(rows, is_option=True):
        lines.append(f"  {b['bucket']:<14} {b['n']:>4} ${b['total_pnl']:>10,.2f} ${b['avg_pnl']:>8,.2f} {b['win_rate_pct']:>5.1f}%")
    lines.append("")
    lines.append("=== Top 10 tickers by net P&L (positive) ===")
    lines.append(f"  {'TKR':<8} {'N':>4} {'TOTAL':>12} {'AVG':>10} {'WIN%':>6}")
    for t in per_ticker(rows)[:10]:
        lines.append(f"  {t['ticker']:<8} {t['n']:>4} ${t['total_pnl']:>10,.2f} ${t['avg_pnl']:>8,.2f} {t['win_rate_pct']:>5.1f}%")
    lines.append("")
    lines.append("=== Bottom 10 tickers by net P&L (negative) ===")
    for t in per_ticker(rows)[-10:]:
        lines.append(f"  {t['ticker']:<8} {t['n']:>4} ${t['total_pnl']:>10,.2f} ${t['avg_pnl']:>8,.2f} {t['win_rate_pct']:>5.1f}%")
    lines.append("")
    top, bot = biggest(rows, k=5)
    lines.append("=== Top 5 biggest wins ===")
    for r in top:
        tag = "OPT" if r.is_option else "EQ "
        lines.append(f"  {tag} {r.underlying:<6} qty={r.quantity:g}  ${r.gl_dollar:+,.2f} ({r.gl_pct or 0:+.1f}%)")
    lines.append("=== Top 5 biggest losses ===")
    for r in bot:
        tag = "OPT" if r.is_option else "EQ "
        lines.append(f"  {tag} {r.underlying:<6} qty={r.quantity:g}  ${r.gl_dollar:+,.2f} ({r.gl_pct or 0:+.1f}%)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if not argv:
        print("usage: python -m research.schwab_feedback <schwab_gainloss.csv>", file=sys.stderr)
        return 2
    csv_path = Path(argv[0])
    if not csv_path.exists():
        print(f"file not found: {csv_path}", file=sys.stderr)
        return 2
    rows = load_rows(csv_path)
    print(_fmt(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
