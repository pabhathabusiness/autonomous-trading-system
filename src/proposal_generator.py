"""
Turns screened candidates into a ranked pool of trade proposals.

Selection is CONFIDENCE-TIER based, not a single hard cutoff: each account
declares the minimum tier it will accept. Rather than a single global
top-N, the generator returns a broader pool -- capped per hot sector -- so
the dashboard can present it three ways:

    * Top     -> the highest-conviction handful (focused)
    * Sector  -> best 3-5 names from each hot sector
    * Timeframe-> grouped into "3-10 days" / "1-3 weeks" / "2-6 weeks"

Ranking prefers higher tiers first; within a tier, "affordable" names
(<= an account's preferred_max_price) float up, then edge count / quality.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Optional

from src.risk_manager import RiskManager
from src.technical_analyzer import TIER_RANK, TechnicalAnalyzer

logger = logging.getLogger(__name__)

TIMEFRAME_BUCKETS = ["3-10 days", "1-3 weeks", "2-6 weeks"]


def timeframe_bucket(weekly_bias: str, num_edges: int) -> str:
    if weekly_bias == "BULLISH" and num_edges >= 8:
        return "2-6 weeks"
    if weekly_bias == "BULLISH" or num_edges >= 6:
        return "1-3 weeks"
    return "3-10 days"


def _reasoning(candidate: dict[str, Any], a: dict[str, Any], regime: dict[str, Any]) -> str:
    pattern_txt = f" Patterns: {', '.join(a['patterns'])}." if a.get("patterns") else ""
    rvol_txt = f" RVOL {a['rvol']}." if a.get("rvol") else ""
    tgt_txt = f" Analyst target {a['analyst_target']}." if a.get("analyst_target") else ""
    return (
        f"{candidate['symbol']} ({candidate['sector_name']}) -- {a['confidence']} confidence "
        f"from {a['num_edges']} edges: {a['edges_fired']}. "
        f"Structure {a['daily_bias']} daily / {a['weekly_bias']} weekly. "
        f"MACD {a['macd_signal']}, Bollinger {a['bb_position'].replace('_', ' ').lower()}, "
        f"RSI {a['rsi']}.{rvol_txt}{pattern_txt}{tgt_txt} "
        f"Entry {a['entry_price']} / stop {a['stop_loss']} / target {a['target_price']} "
        f"= {a['risk_reward']}:1 R:R. Market regime: {regime.get('regime', 'NEUTRAL')}."
    )


class ProposalGenerator:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.technical_analyzer = TechnicalAnalyzer(config)
        self.risk_manager = RiskManager(config)

    def generate(
        self,
        account_type: str,
        screened_stocks: list[dict[str, Any]],
        market_regime: dict[str, Any],
        account_balance: float,
    ) -> list[dict[str, Any]]:
        account_cfg = self.config["accounts"][account_type]
        min_confidence = account_cfg.get("min_confidence", "MEDIUM").upper()
        min_rank = TIER_RANK.get(min_confidence, 2)
        max_per_sector = account_cfg.get("max_per_sector", 5)
        max_total = account_cfg.get("max_total_proposals", 20)
        preferred_max = account_cfg.get("preferred_max_price")
        # Swing is the longest hold and ties up capital longest, so it must
        # demand the best reward: floor 2.0 (a 50% win rate at 2:1 is solidly
        # profitable after costs). This is the quality GATE, not the edge logic.
        min_risk_reward = account_cfg.get("min_risk_reward", 2.0)

        regime_name = market_regime.get("regime")
        if regime_name == "BEAR" and account_cfg.get("pause_new_entries_on_bear", False):
            logger.info("[%s] Skipping: BEAR regime and pause_new_entries_on_bear=True", account_type)
            return []
        if regime_name == "BEAR":
            min_rank = min(TIER_RANK["HIGH"], min_rank + 1)

        scored: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for candidate in screened_stocks:
            analysis = self.technical_analyzer.analyze(candidate["symbol"], fundamentals=candidate)
            if analysis is None:
                continue
            # microfloat names may qualify one tier lower (higher-risk, small size)
            effective_min = min_rank - 1 if candidate.get("is_microfloat") else min_rank
            if TIER_RANK.get(analysis["confidence"], 0) < max(TIER_RANK["LOW"], effective_min):
                continue
            if analysis["risk_reward"] < min_risk_reward:
                logger.debug("Skipping %s: R:R %.2f below floor %.2f",
                             candidate["symbol"], analysis["risk_reward"], min_risk_reward)
                continue
            scored.append((candidate, analysis))

        def affordable(candidate: dict[str, Any]) -> int:
            if preferred_max is None:
                return 1
            return 1 if candidate["price"] <= preferred_max else 0

        # tier first (never let a cheap LOW jump a HIGH), then affordability,
        # then edge count, then quality.
        scored.sort(key=lambda pair: (
            TIER_RANK[pair[1]["confidence"]],
            affordable(pair[0]),
            pair[1]["num_edges"],
            pair[1]["quality_score"],
        ), reverse=True)

        proposals: list[dict[str, Any]] = []
        per_sector: dict[str, int] = defaultdict(int)
        for candidate, a in scored:
            if len(proposals) >= max_total:
                break
            sector = candidate["sector_name"]
            if per_sector[sector] >= max_per_sector:
                continue
            sizing = self.risk_manager.calculate_position_size(
                account_type=account_type,
                entry_price=a["entry_price"],
                stop_loss=a["stop_loss"],
                quality_score=a["quality_score"],
                account_balance=account_balance,
                risk_scale=0.5 if candidate.get("is_microfloat") else 1.0,
            )
            if sizing is None:
                continue
            per_sector[sector] += 1
            proposals.append({
                "account_type": account_type,
                "symbol": candidate["symbol"],
                "sector_name": sector,
                "entry_price": a["entry_price"],
                "stop_loss": a["stop_loss"],
                "target_price": a["target_price"],
                "risk_reward": a["risk_reward"],
                "quality_score": a["quality_score"],
                "confidence": a["confidence"],
                "num_edges": a["num_edges"],
                "edges_fired": a["edges_fired"],
                "strategy": "swing",
                "is_microfloat": bool(candidate.get("is_microfloat")),
                "position_size_usd": sizing["position_size_usd"],
                "shares": sizing["shares"],
                "risk_amount": sizing["risk_amount"],
                "expected_return_pct": a["expected_return_pct"],
                "expected_timeframe": timeframe_bucket(a["weekly_bias"], a["num_edges"]),
                "reasoning": _reasoning(candidate, a, market_regime),
                "_analysis": a,
            })

        logger.info(
            "[%s] %d proposals across %d sectors (min_confidence=%s, regime=%s)",
            account_type, len(proposals), len(per_sector), min_confidence, regime_name,
        )
        return proposals
