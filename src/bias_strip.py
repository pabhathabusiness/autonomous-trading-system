"""
Market-bias strip data for the dashboard's top row (SPY + mega-caps).

Presentation of things already computed elsewhere -- structure bias, nearest
pivots, EMAs -- merged with Alpaca's live price. The STRUCTURAL read (bias +
key levels) is cached per symbol (~10 min) because it only moves on new daily
bars; only the live price/age is refreshed on every call, so a 5s dashboard
poll never re-downloads daily history for eight names.

Daily bars for the structural read come from Alpaca first -- it's the market
data API this account actually holds working credentials for, and one batched
call covers every symbol instead of N sequential round-trips. yfinance (an
unauthenticated, unofficial scrape) is only a fallback for when Alpaca is
disabled or a symbol's bars come back empty.

Bias is CONDITIONAL, never a forecast: the frontend renders it as
"Bullish above X / watch Y below" using level_above / level_below.
"""

from __future__ import annotations

import time
from typing import Any, Optional

import pandas as pd
import yfinance as yf

from src import indicators

_CACHE: dict[str, dict[str, Any]] = {}
_TTL = 600  # seconds


def _structural(symbol: str, df: Optional[pd.DataFrame] = None) -> Optional[dict[str, Any]]:
    """Daily structure read for one symbol (cached). Bias + nearest key levels.
    Takes an optional pre-fetched (Alpaca) daily-bars frame; falls back to a
    yfinance history pull when none is supplied or it's too thin to use."""
    hit = _CACHE.get(symbol)
    if hit and time.time() - hit["ts"] < _TTL:
        return hit["data"]
    if df is None or df.empty or len(df) < 30:
        try:
            df = yf.Ticker(symbol).history(period="1y", interval="1d", auto_adjust=True)
        except Exception:
            df = None
    if df is None or df.empty or len(df) < 30:
        return None
    closes = df["Close"]
    price = float(closes.iloc[-1])
    prev_close = float(closes.iloc[-2])
    highs, lows = indicators.find_pivots(df, 3)
    struct = indicators.structure_bias(highs, lows)
    ema20, ema50 = indicators.ema(closes, 20), indicators.ema(closes, 50)
    up = bool(ema20 and ema50 and price > ema20 > ema50)
    down = bool(ema20 and ema50 and price < ema20 < ema50)
    bullish = (struct == "BULLISH") or up
    bearish = (struct == "BEARISH") or down
    if bullish and not bearish:
        bias = "Bullish"
    elif bearish and not bullish:
        bias = "Bearish"
    else:
        bias = "Neutral"
    data = {
        "bias": bias,
        "level_above": indicators.nearest_level(highs, price, "above"),
        "level_below": indicators.nearest_level(lows, price, "below"),
        "prev_close": prev_close,
        "last_close": price,
    }
    _CACHE[symbol] = {"ts": time.time(), "data": data}
    return data


def build(alpaca, symbols: list[str]) -> list[dict[str, Any]]:
    enabled = getattr(alpaca, "enabled", False)
    live = alpaca.latest_prices(symbols) if enabled else {}
    # One batched call for every symbol's daily bars, instead of N sequential
    # yfinance scrapes -- also what makes this resilient when yfinance itself
    # is unreachable (rate-limited, blocked, whatever) but Alpaca is fine.
    daily_bars = alpaca.bars(symbols, "1d", limit=260) if enabled else {}
    out: list[dict[str, Any]] = []
    for sym in symbols:
        st = _structural(sym, daily_bars.get(sym))
        info = live.get(sym, {})
        lp = info.get("price")
        if lp is None and st:
            lp = st["last_close"]
        prev = st["prev_close"] if st else None
        session_pct = round((lp - prev) / prev * 100, 2) if (lp and prev) else None
        out.append({
            "symbol": sym,
            "price": lp,
            "session_pct": session_pct,
            # None (no data) is distinct from a real "Neutral" read -- collapsing
            # them made a symbol we simply couldn't fetch look identically
            # assessed to one that's genuinely flat.
            "bias": st["bias"] if st else None,
            "level_above": st["level_above"] if st else None,
            "level_below": st["level_below"] if st else None,
            "age_seconds": info.get("age_seconds"),
        })
    return out
