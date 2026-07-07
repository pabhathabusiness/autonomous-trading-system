"""
Dynamic position sizing: how many shares to propose given an account's
balance, its risk profile (aggressive penny-stock bot vs. selective
personal account), the entry/stop distance, and the setup's quality score.
"""

from __future__ import annotations

import math
from typing import Any, Optional


class RiskManager:
    def __init__(self, config: dict[str, Any]):
        self.accounts_config = config["accounts"]

    def _quality_multiplier(self, quality_score: float, threshold: float) -> float:
        """Scale risk taken between 0.7x (right at threshold) and 1.0x
        (at or above a quality_score of 10)."""
        if quality_score >= 10:
            return 1.0
        if quality_score <= threshold:
            return 0.7
        span = 10 - threshold
        return 0.7 + 0.3 * (quality_score - threshold) / span

    def calculate_position_size(
        self,
        account_type: str,
        entry_price: float,
        stop_loss: float,
        quality_score: float,
        account_balance: float,
        risk_scale: float = 1.0,
    ) -> Optional[dict[str, Any]]:
        cfg = self.accounts_config[account_type]
        max_risk_pct = cfg.get("max_risk_per_trade_pct", 5.0)
        quality_threshold = cfg.get("quality_threshold", 7.5)

        # distance to stop -- works for longs (stop below) and shorts (stop above)
        risk_per_share = abs(entry_price - stop_loss)
        if risk_per_share <= 0 or entry_price <= 0:
            return None

        multiplier = self._quality_multiplier(quality_score, quality_threshold)
        # risk_scale < 1 -> smaller position (e.g. 0.5 for higher-risk microfloat)
        risk_amount = account_balance * (max_risk_pct / 100) * multiplier * risk_scale

        shares = math.floor(risk_amount / risk_per_share)
        position_size_usd = shares * entry_price

        # never propose spending more cash than the account actually has
        if position_size_usd > account_balance:
            shares = math.floor(account_balance / entry_price)
            position_size_usd = shares * entry_price

        if shares < 1:
            return None

        actual_risk_amount = shares * risk_per_share
        return {
            "shares": shares,
            "position_size_usd": round(position_size_usd, 2),
            "risk_amount": round(actual_risk_amount, 2),
            "risk_pct_of_account": round(actual_risk_amount / account_balance * 100, 2),
            "quality_multiplier": round(multiplier, 3),
        }
