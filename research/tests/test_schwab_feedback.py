"""Tests for research.schwab_feedback — Schwab CSV parser + aggregators."""

from __future__ import annotations

import textwrap
from datetime import datetime
from pathlib import Path

import pytest

from research import schwab_feedback as sf


def _write(tmp_path: Path, contents: str) -> Path:
    p = tmp_path / "sample.csv"
    p.write_text(textwrap.dedent(contents).lstrip("\n"))
    return p


SAMPLE = """
"Realized Gain/Loss - Lot Details for ...615 as of Wed Sep 16  10:16:58 EDT 2026 from 06/16/2026 to 09/16/2026","","","","","","","","","","","","","","","","","","","","","","","",""
"Symbol","Name","Closed Date","Opened Date","Quantity","Proceeds Per Share","Cost Per Share","Proceeds","Cost Basis (CB)","Gain/Loss ($)","Gain/Loss (%)","Long Term Gain/Loss","Short Term Gain/Loss","Term","Unadjusted Cost Basis","Wash Sale?","Disallowed Loss","Transaction Closed Date","Transaction Cost Basis","Total Transaction Gain/Loss ($)","Total Transaction Gain/Loss (%)","LT Transaction Gain/Loss ($)","LT Transaction Gain/Loss (%)","ST Transaction Gain/Loss ($)","ST Transaction Gain/Loss (%)"
"AAPL 09/16/2026 337.50 C","CALL APPLE INC $337.5 EXP 09/16/26","09/16/2026","09/16/2026","1","$0.67","$0.54","$67.34","$53.66","$13.68","25.49%","","$13.68","Short Term","$53.66","No","","09/16/2026","","","","","","",""
"AAPL 09/16/2026 337.50 C","CALL APPLE INC $337.5 EXP 09/16/26","09/16/2026","09/16/2026","1","$0.40","$0.52","$40.34","$51.98","-$11.64","-22.39%","","-$11.64","Short Term","$51.98","Yes","$11.64","09/16/2026","$42.66","-$2.32","-5.44%","","","-$2.32","-5.44%"
"NVDA","NVIDIA CORP","07/01/2026","06/20/2026","10","$140.00","$130.00","$1,400.00","$1,300.00","$100.00","7.69%","","$100.00","Short Term","$1,300.00","No","","07/01/2026","","","","","","",""
"SPY 07/03/2026 550.00 P","PUT SPY","07/03/2026","07/01/2026","2","$0.00","$0.85","$0.00","$170.00","-$170.00","-100.00%","","-$170.00","Short Term","$170.00","No","","07/03/2026","","","","","","",""
"""


def test_load_rows_shape(tmp_path):
    p = _write(tmp_path, SAMPLE)
    rows = sf.load_rows(p)
    assert len(rows) == 4
    assert [r.underlying for r in rows] == ["AAPL", "AAPL", "NVDA", "SPY"]
    opts = [r for r in rows if r.is_option]
    eqs = [r for r in rows if not r.is_option]
    assert len(opts) == 3 and len(eqs) == 1


def test_option_parse():
    r = sf.load_rows(_write_tmp())[0]
    assert r.is_option is True
    assert r.option_side == "C"
    assert r.option_strike == 337.5
    assert r.option_expiry == datetime(2026, 9, 16)


def _write_tmp() -> Path:
    import tempfile
    d = Path(tempfile.mkdtemp())
    p = d / "s.csv"
    p.write_text(textwrap.dedent(SAMPLE).lstrip("\n"))
    return p


def test_money_and_pct_parsing():
    assert sf._parse_money("$1,234.56") == 1234.56
    assert sf._parse_money("-$11.64") == -11.64
    assert sf._parse_money("") is None
    assert sf._parse_pct("25.49%") == 25.49
    assert sf._parse_pct("-22.39%") == -22.39
    assert sf._parse_pct("") is None


def test_summarize_basics(tmp_path):
    rows = sf.load_rows(_write(tmp_path, SAMPLE))
    s = sf.summarize(rows, "all")
    assert s["n"] == 4
    assert s["n_win"] == 2      # AAPL +$13.68, NVDA +$100
    assert s["n_loss"] == 2     # AAPL -$11.64, SPY -$170
    assert round(s["total_pnl"], 2) == round(13.68 + 100 - 11.64 - 170, 2)
    assert s["win_rate_pct"] == pytest.approx(50.0)


def test_by_dte_puts_zerodte_lots(tmp_path):
    rows = sf.load_rows(_write(tmp_path, SAMPLE))
    buckets = {b["bucket"]: b for b in sf.by_dte(rows)}
    # AAPL calls opened & expire same day → 0DTE (two lots)
    # SPY put 07/03 opened 07/01 → 2DTE (bucket "2-5DTE")
    assert buckets["0DTE"]["n"] == 2
    assert buckets["2-5DTE"]["n"] == 1


def test_by_days_held(tmp_path):
    rows = sf.load_rows(_write(tmp_path, SAMPLE))
    # equity NVDA held 11 days → "8-14" bucket
    eq_buckets = {b["bucket"]: b for b in sf.by_days_held(rows, is_option=False)}
    assert eq_buckets["8-14"]["n"] == 1
    # options: 2 AAPL same-day (0), 1 SPY 2-day
    opt_buckets = {b["bucket"]: b for b in sf.by_days_held(rows, is_option=True)}
    assert opt_buckets["0 (intraday)"]["n"] == 2
    assert opt_buckets["2-3"]["n"] == 1


def test_per_ticker_sorted_by_pnl(tmp_path):
    rows = sf.load_rows(_write(tmp_path, SAMPLE))
    ranked = sf.per_ticker(rows)
    tkrs = [r["ticker"] for r in ranked]
    # NVDA is best (+100), SPY is worst (-170); AAPL two lots net +2.04
    assert tkrs[0] == "NVDA"
    assert tkrs[-1] == "SPY"


def test_wash_sale_report(tmp_path):
    rows = sf.load_rows(_write(tmp_path, SAMPLE))
    w = sf.wash_sale_report(rows)
    assert w["n_lots_flagged"] == 1
    assert w["disallowed_loss_total"] == 11.64


def test_empty_csv(tmp_path):
    p = _write(tmp_path, '"nothing","here"\n"Symbol","Name","Closed Date","Opened Date","Quantity","Proceeds Per Share","Cost Per Share","Proceeds","Cost Basis (CB)","Gain/Loss ($)","Gain/Loss (%)","Long Term Gain/Loss","Short Term Gain/Loss","Term","Unadjusted Cost Basis","Wash Sale?","Disallowed Loss","Transaction Closed Date","Transaction Cost Basis","Total Transaction Gain/Loss ($)","Total Transaction Gain/Loss (%)","LT Transaction Gain/Loss ($)","LT Transaction Gain/Loss (%)","ST Transaction Gain/Loss ($)","ST Transaction Gain/Loss (%)"\n')
    rows = sf.load_rows(p)
    assert rows == []
    assert sf.summarize(rows)["n"] == 0
