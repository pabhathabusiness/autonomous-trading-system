"""Layer-2 semantic regime.

Two axes (trend × risk), full state stored per occurrence. Coarse buckets
are REPORT-ONLY collapses of the full state — never overwrite or replace it.

Aligns with the Telegram bot's naming (`TRENDING_DOWN`, `RISK_OFF`, ...) as
observed in alerts. Exact bot semantics reconciled when the bot repo is
attached; version bump if the taxonomy diverges.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd


Trend = Literal["STRONG_UPTREND", "UPTREND", "SIDEWAYS", "DOWNTREND", "STRONG_DOWNTREND", "UNKNOWN"]
Risk = Literal["RISK_ON", "RISK_NEUTRAL", "RISK_OFF", "UNKNOWN"]

CoarseBucket = Literal["BULL_ENV", "BEAR_ENV", "CHOP", "UNKNOWN"]


@dataclass(frozen=True)
class SemanticRegime:
    trend: Trend
    risk: Risk

    @property
    def label(self) -> str:
        return f"{self.trend}+{self.risk}"

    @property
    def coarse(self) -> CoarseBucket:
        if self.trend == "UNKNOWN" or self.risk == "UNKNOWN":
            return "UNKNOWN"
        if self.trend == "STRONG_UPTREND":
            return "BULL_ENV"
        if self.trend == "UPTREND" and self.risk in ("RISK_ON", "RISK_NEUTRAL"):
            return "BULL_ENV"
        if self.trend == "STRONG_DOWNTREND":
            return "BEAR_ENV"
        if self.trend == "DOWNTREND" and self.risk in ("RISK_OFF", "RISK_NEUTRAL"):
            return "BEAR_ENV"
        return "CHOP"


# --------------------------------------------------------------------- helpers
def _ema(x: pd.Series, span: int) -> pd.Series:
    return x.ewm(span=span, adjust=False).mean()


def _roc(x: pd.Series, periods: int) -> pd.Series:
    return (x / x.shift(periods) - 1.0) * 100.0


def _true_range(df: pd.DataFrame) -> pd.Series:
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift(1)).abs()
    lc = (df["low"] - df["close"].shift(1)).abs()
    return pd.concat([hl, hc, lc], axis=1).max(axis=1)


def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    return _true_range(df).rolling(period).mean()


# --------------------------------------------------------------------- axes
def _trend_state(closes: pd.Series) -> Trend:
    if len(closes) < 55:
        return "UNKNOWN"
    e9 = _ema(closes, 9).iloc[-1]
    e20 = _ema(closes, 20).iloc[-1]
    e21 = _ema(closes, 21).iloc[-1]
    e50 = _ema(closes, 50).iloc[-1]
    c = float(closes.iloc[-1])
    roc30 = float(_roc(closes, 30).iloc[-1]) if len(closes) > 30 else float("nan")
    if not np.isfinite(roc30):
        return "UNKNOWN"

    if e9 > e21 > e50 and c > e20 and roc30 > 5:
        return "STRONG_UPTREND"
    if e20 > e50 and c > e20 and 2 < roc30 <= 5:
        return "UPTREND"
    if e9 < e21 < e50 and c < e20 and roc30 < -5:
        return "STRONG_DOWNTREND"
    if e20 < e50 and c < e20 and -5 <= roc30 < -2:
        return "DOWNTREND"
    return "SIDEWAYS"


def _risk_state(df: pd.DataFrame) -> Risk:
    if len(df) < 60:
        return "UNKNOWN"
    closes = df["close"]
    c = float(closes.iloc[-1])
    lo60 = float(closes.tail(60).min())
    hi60 = float(closes.tail(60).max())
    rng = hi60 - lo60 if hi60 > lo60 else 1.0
    pct_in_range = (c - lo60) / rng  # 0 = at low, 1 = at high

    atr14 = _atr(df, 14)
    atr_last = float(atr14.iloc[-1])
    atr_mean_60 = float(atr14.tail(60).mean())
    ratio = atr_last / atr_mean_60 if atr_mean_60 > 0 else float("nan")

    if not np.isfinite(ratio):
        return "UNKNOWN"

    if pct_in_range >= 0.8 and ratio < 1.2:
        return "RISK_ON"
    if pct_in_range <= 0.2 or ratio > 1.5:
        return "RISK_OFF"
    return "RISK_NEUTRAL"


# --------------------------------------------------------------------- API
def semantic_regime_at(spy_df: pd.DataFrame, timestamp: pd.Timestamp) -> SemanticRegime:
    """Full Layer-2 state at (or immediately before) `timestamp`. If SPY doesn't
    have that exact timestamp, uses the most recent SPY bar ≤ timestamp."""
    if spy_df is None or spy_df.empty:
        return SemanticRegime("UNKNOWN", "UNKNOWN")
    idx = spy_df.index.searchsorted(timestamp, side="right") - 1
    if idx < 0:
        return SemanticRegime("UNKNOWN", "UNKNOWN")
    slice_ = spy_df.iloc[: idx + 1]
    trend = _trend_state(slice_["close"])
    risk = _risk_state(slice_)
    return SemanticRegime(trend, risk)


def semantic_regime_series(spy_df: pd.DataFrame) -> pd.Series:
    """One label per bar. Slow (O(n) per bar); use only for offline tagging.

    Returns a Series of SemanticRegime.label strings, indexed by spy_df.index.
    """
    if spy_df is None or spy_df.empty:
        return pd.Series(dtype=object)
    labels = []
    for i in range(len(spy_df)):
        s = spy_df.iloc[: i + 1]
        r = SemanticRegime(_trend_state(s["close"]), _risk_state(s))
        labels.append(r.label)
    return pd.Series(labels, index=spy_df.index)
