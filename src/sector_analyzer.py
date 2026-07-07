"""
Ranks sectors (via ETF proxies) by multi-timeframe performance so the
screener only searches for penny stocks inside sectors that are actually
"hot" right now.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


def _pct_change(closes: pd.Series, periods: int) -> float:
    if len(closes) <= periods:
        return 0.0
    start = closes.iloc[-periods - 1]
    end = closes.iloc[-1]
    if start == 0:
        return 0.0
    return float((end - start) / start * 100)


class SectorAnalyzer:
    def __init__(self, config: dict[str, Any]):
        scfg = config.get("sectors", {})
        self.top_n = scfg.get("top_n_hot_sectors", 8)
        self.weights = scfg.get(
            "trend_weights", {"1d": 0.15, "5d": 0.30, "10d": 0.30, "30d": 0.25}
        )
        universe_path = config.get("universe", {}).get(
            "sector_tickers_file", "config/universe.json"
        )
        self.universe = self._load_universe(universe_path)

    @staticmethod
    def _load_universe(path: str) -> list[dict[str, Any]]:
        with open(Path(path), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data["sectors"]

    def _fetch_etf_history(self, symbols: list[str]) -> dict[str, pd.DataFrame]:
        raw = yf.download(
            symbols, period="6mo", interval="1d", progress=False,
            auto_adjust=True, group_by="ticker",
        )
        out: dict[str, pd.DataFrame] = {}
        for sym in symbols:
            try:
                df = raw[sym] if isinstance(raw.columns, pd.MultiIndex) else raw
                if df is not None and not df.empty:
                    out[sym] = df.dropna()
            except (KeyError, TypeError):
                logger.warning("No history for sector ETF %s", sym)
        return out

    def analyze(self) -> list[dict[str, Any]]:
        etfs = [s["etf"] for s in self.universe]
        history = self._fetch_etf_history(etfs)

        rankings: list[dict[str, Any]] = []
        for sector in self.universe:
            df = history.get(sector["etf"])
            if df is None or df.empty:
                continue
            closes = df["Close"]
            perf_1d = _pct_change(closes, 1)
            perf_5d = _pct_change(closes, 5)
            perf_10d = _pct_change(closes, 10)
            perf_30d = _pct_change(closes, 30)
            composite = (
                self.weights["1d"] * perf_1d
                + self.weights["5d"] * perf_5d
                + self.weights["10d"] * perf_10d
                + self.weights["30d"] * perf_30d
            )
            rankings.append({
                "sector_name": sector["name"],
                "etf_symbol": sector["etf"],
                "perf_1d": round(perf_1d, 2),
                "perf_5d": round(perf_5d, 2),
                "perf_10d": round(perf_10d, 2),
                "perf_30d": round(perf_30d, 2),
                "composite_score": round(composite, 3),
            })

        rankings.sort(key=lambda r: r["composite_score"], reverse=True)
        for i, r in enumerate(rankings, start=1):
            r["rank"] = i

        logger.info("Ranked %d/%d sectors", len(rankings), len(self.universe))
        return rankings

    def hot_sectors(self, rankings: list[dict[str, Any]]) -> list[str]:
        return [r["sector_name"] for r in rankings[: self.top_n]]

    @staticmethod
    def turning_sectors(rankings: list[dict[str, Any]], limit: int = 4) -> list[str]:
        """Laggard-rotation: sectors that are WEAK longer-term (30d down) but
        starting to turn UP short-term (5d positive) -- the 'bottleneck sector
        about to get bid' that isn't officially hot yet. Ranked by how strong
        the short-term turn is relative to the longer-term weakness."""
        turning = []
        for r in rankings:
            long_wk = (r.get("perf_30d") or 0) < 0
            short_up = (r.get("perf_5d") or 0) > 0 and (r.get("perf_1d") or 0) > 0
            if long_wk and short_up:
                turn_score = (r.get("perf_5d") or 0) + (r.get("perf_1d") or 0) - (r.get("perf_30d") or 0)
                turning.append((turn_score, r["sector_name"]))
        turning.sort(reverse=True)
        return [name for _, name in turning[:limit]]

    def candidates_for_sector(self, sector_name: str) -> list[str]:
        for sector in self.universe:
            if sector["name"] == sector_name:
                return sector["candidates"]
        return []

    def analyze_and_store(self, db) -> tuple[list[dict[str, Any]], list[str]]:
        rankings = self.analyze()
        db.insert_sector_rankings(rankings)
        return rankings, self.hot_sectors(rankings)
