"""
Screens candidate tickers from hot sectors down to a shortlist that fits
an account's price/volume/fundamentals profile (e.g. sub-$5 penny stocks
with real volume for the aggressive bot, broader multi-asset names for
the personal account).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import yfinance as yf

logger = logging.getLogger(__name__)


class Screener:
    def __init__(self, config: dict[str, Any], account_type: str):
        self.account_type = account_type
        account_cfg = config["accounts"][account_type]
        self.min_price, self.max_price = account_cfg.get("price_range", [0.5, 5])
        self.min_volume = account_cfg.get("min_volume", 500_000)
        # Optional Finviz-style hard filters (default off -> treated as edges).
        self.require_rvol_over = account_cfg.get("require_rvol_over")  # e.g. 1.0
        self.require_target_above_price = account_cfg.get("require_target_above_price", False)
        # Quality gates (HARD: OTC + liquidity; SOFT: revenue/growth via score).
        qf = config.get("quality_filters", {})
        self.exclude_otc = qf.get("exclude_otc", True)
        self.min_avg_volume = qf.get("min_avg_volume", 1_000_000)
        self.microfloat_shares = qf.get("microfloat_shares", 20_000_000)
        self.otc_exchanges = {"PNK", "OTC", "OTCBB", "OTCQB", "OTCQX", "OQB", "OQX", "PINX", "EXPM"}

    def _fetch_fundamentals(self, symbol: str) -> Optional[dict[str, Any]]:
        try:
            ticker = yf.Ticker(symbol)
            fast = ticker.fast_info
            price = fast.get("lastPrice") or fast.get("last_price")
            volume = fast.get("lastVolume") or fast.get("last_volume")
            market_cap = fast.get("marketCap") or fast.get("market_cap")
            if price is None or volume is None:
                return None

            revenue = None
            revenue_growth = None
            price_target = None
            avg_volume = None
            float_shares = None
            exchange = None
            try:
                info = ticker.info
                revenue = info.get("totalRevenue")
                revenue_growth = info.get("revenueGrowth")  # YoY, e.g. 0.15 = +15%
                if not market_cap:
                    market_cap = info.get("marketCap")
                price_target = info.get("targetMeanPrice") or info.get("targetMedianPrice")
                avg_volume = info.get("averageVolume") or info.get("averageDailyVolume10Day")
                float_shares = info.get("floatShares") or info.get("sharesOutstanding")
                exchange = info.get("exchange")
            except Exception:
                pass

            rvol = (float(volume) / float(avg_volume)) if avg_volume else None
            return {
                "price": float(price),
                "volume": int(volume),
                "avg_volume": float(avg_volume) if avg_volume else None,
                "market_cap": float(market_cap) if market_cap else None,
                "revenue": float(revenue) if revenue else None,
                "revenue_growth": float(revenue_growth) if revenue_growth is not None else None,
                "price_target": float(price_target) if price_target else None,
                "rvol": round(rvol, 2) if rvol else None,
                "float_shares": float(float_shares) if float_shares else None,
                "is_microfloat": bool(float_shares and float_shares < self.microfloat_shares),
                "exchange": exchange,
            }
        except Exception as exc:
            logger.debug("Skipping %s: %s", symbol, exc)
            return None

    def _passes_filters(self, data: dict[str, Any]) -> bool:
        if not (self.min_price <= data["price"] <= self.max_price):
            return False
        if data["volume"] < self.min_volume:
            return False
        # HARD: no OTC / pink-sheet names
        if self.exclude_otc and (data.get("exchange") or "").upper() in self.otc_exchanges:
            return False
        # HARD: real liquidity -- average volume must clear the floor
        if self.min_avg_volume and data.get("avg_volume") is not None:
            if data["avg_volume"] < self.min_avg_volume:
                return False
        if self.require_rvol_over is not None:
            if data.get("rvol") is None or data["rvol"] < self.require_rvol_over:
                return False
        if self.require_target_above_price:
            target = data.get("price_target")
            if target is None or target <= data["price"]:
                return False
        return True

    def _fundamentals_score(self, data: dict[str, Any]) -> float:
        """SOFT quality score (0-1) blending: is there a real business
        (revenue vs market cap), is revenue GROWING year-over-year, and a
        best-effort distress/bankruptcy proxy. Never disqualifies on its own
        -- just ranks weaker names lower."""
        market_cap = data.get("market_cap")
        revenue = data.get("revenue")
        growth = data.get("revenue_growth")

        # base: revenue-to-market-cap (real business proxy)
        if not market_cap or market_cap <= 0 or revenue is None:
            base = 0.3  # unknown / pre-revenue: neutral-low, not disqualifying
        else:
            base = max(0.0, min(1.0, (revenue / market_cap) * 2))

        # growth bonus: growing revenue YoY lifts the score, shrinking lowers it
        if growth is not None:
            base += 0.25 if growth > 0.15 else 0.10 if growth > 0 else -0.20

        # best-effort distress proxy: no revenue AND shrinking is a red flag
        if (revenue is None or revenue <= 0) and (growth is not None and growth < 0):
            base -= 0.15

        return round(max(0.0, min(1.0, base)), 3)

    def run(self, hot_sectors: list[str], sector_analyzer) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        seen: set[str] = set()

        for sector_name in hot_sectors:
            for symbol in sector_analyzer.candidates_for_sector(sector_name):
                if symbol in seen:
                    continue
                seen.add(symbol)

                data = self._fetch_fundamentals(symbol)
                if data is None or not self._passes_filters(data):
                    continue

                fundamentals_score = self._fundamentals_score(data)
                rev_to_mcap = (
                    data["revenue"] / data["market_cap"]
                    if data.get("revenue") and data.get("market_cap")
                    else None
                )
                results.append({
                    "account_type": self.account_type,
                    "symbol": symbol,
                    "sector_name": sector_name,
                    "price": round(data["price"], 4),
                    "volume": data["volume"],
                    "market_cap": data.get("market_cap"),
                    "revenue": data.get("revenue"),
                    "rev_to_mcap_ratio": round(rev_to_mcap, 4) if rev_to_mcap else None,
                    "revenue_growth": data.get("revenue_growth"),
                    "fundamentals_score": round(fundamentals_score, 3),
                    # carried through to the technical analyzer as fundamentals
                    "rvol": data.get("rvol"),
                    "price_target": data.get("price_target"),
                    "float_shares": data.get("float_shares"),
                    "is_microfloat": data.get("is_microfloat", False),
                })

        logger.info(
            "[%s] Screened %d candidates down to %d that pass price/volume filters",
            self.account_type, len(seen), len(results),
        )
        return results
