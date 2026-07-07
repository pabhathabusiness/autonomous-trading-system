"""
Market regime detection: is the broad market (SPY) in a BULL, BEAR, or
NEUTRAL regime, and is it overbought/oversold enough to warrant caution.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


def _rsi(closes: pd.Series, period: int = 14) -> float:
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    value = rsi.iloc[-1]
    return float(value) if pd.notna(value) else 50.0


def _pct_change(closes: pd.Series, periods: int) -> Optional[float]:
    if len(closes) <= periods:
        return None
    start = closes.iloc[-periods - 1]
    end = closes.iloc[-1]
    if start == 0:
        return None
    return float((end - start) / start * 100)


class MarketAnalyzer:
    """Detects overall market regime from a benchmark symbol (default SPY)."""

    def __init__(self, config: dict[str, Any]):
        mcfg = config.get("market_regime", {})
        self.symbol = mcfg.get("symbol", "SPY")
        self.overbought_rsi = mcfg.get("overbought_rsi", 70)
        self.oversold_rsi = mcfg.get("oversold_rsi", 30)
        self.bull_threshold = mcfg.get("bull_threshold_pct", 2.0)
        self.bear_threshold = mcfg.get("bear_threshold_pct", -2.0)
        # recent timeframes matter more than distant ones
        self.weights = mcfg.get("trend_weights", {"1d": 0.15, "5d": 0.30, "10d": 0.30, "30d": 0.25})

    def _fetch_history(self) -> pd.DataFrame:
        data = yf.download(self.symbol, period="6mo", interval="1d", progress=False, auto_adjust=True)
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        return data

    def analyze(self) -> dict[str, Any]:
        data = self._fetch_history()
        if data.empty:
            logger.warning("No data returned for %s; defaulting to NEUTRAL", self.symbol)
            return {
                "symbol": self.symbol, "regime": "NEUTRAL", "price": None,
                "trend_30d": None, "trend_10d": None, "trend_5d": None, "trend_1d": None,
                "rsi": 50.0, "condition": "NORMAL", "composite_score": 0.0,
            }

        closes = data["Close"].dropna()
        price = float(closes.iloc[-1])
        trend_1d = _pct_change(closes, 1) or 0.0
        trend_5d = _pct_change(closes, 5) or 0.0
        trend_10d = _pct_change(closes, 10) or 0.0
        trend_30d = _pct_change(closes, 30) or 0.0
        rsi = _rsi(closes)

        composite = (
            self.weights["1d"] * trend_1d
            + self.weights["5d"] * trend_5d
            + self.weights["10d"] * trend_10d
            + self.weights["30d"] * trend_30d
        )

        if composite >= self.bull_threshold:
            regime = "BULL"
        elif composite <= self.bear_threshold:
            regime = "BEAR"
        else:
            regime = "NEUTRAL"

        if rsi >= self.overbought_rsi:
            condition = "OVERBOUGHT"
        elif rsi <= self.oversold_rsi:
            condition = "OVERSOLD"
        else:
            condition = "NORMAL"

        result = {
            "symbol": self.symbol,
            "regime": regime,
            "price": round(price, 2),
            "trend_30d": round(trend_30d, 2),
            "trend_10d": round(trend_10d, 2),
            "trend_5d": round(trend_5d, 2),
            "trend_1d": round(trend_1d, 2),
            "rsi": round(rsi, 2),
            "condition": condition,
            "composite_score": round(composite, 3),
        }
        logger.info("Market regime: %s", result)
        return result

    def analyze_and_store(self, db) -> dict[str, Any]:
        result = self.analyze()
        db.insert_market_regime(result)
        return result
