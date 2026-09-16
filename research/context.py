"""Context orchestrator — compose every v0.3 layer at a single bar t.

Given (symbol, stock_df, spy_df, t, planned_risk_unit), returns a flat
namespaced dict combining supply/demand, relative-strength, market
regime, SMA trend, MACD momentum, and BB/TTM volatility fields.

The orchestrator adds NO new features and NO composite. It is a
composition of per-layer `context_at()` functions plus a small identity
block. Everything else — detectors, cells, reports — reads this dict.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from . import supply_demand as sd
from . import relative_strength as rs
from . import regime as rg
from . import sma_trend as smat
from . import momentum as mom
from . import volatility as vol
from . import versioning as V


def compute_context_at(symbol: str, stock_df: pd.DataFrame,
                       spy_df: pd.DataFrame | None,
                       t: int, planned_risk_unit: float,
                       *, precomputed_zones: list[sd.Zone] | None = None) -> dict[str, Any]:
    """Compute the full v0.3 context record at bar t of `stock_df`.

    - `stock_df` must have ['open','high','low','close'] and a DatetimeIndex.
    - `spy_df` is used for market regime, relative strength, and SPY-side
      SMA fields. May be None (those fields become UNAVAILABLE).
    - `planned_risk_unit` is the frozen signal-time risk unit (E − S).

    Returns a flat dict with the following namespaces:
      identity.*, supply_demand.*, relative_strength.*, market.*,
      trend.*, momentum.*, compression_volatility.*, provenance.*
    """
    if t < 0 or t >= len(stock_df):
        raise IndexError(f"t={t} out of range for stock_df of length {len(stock_df)}")

    bar_ts = stock_df.index[t]

    out: dict[str, Any] = {
        "identity.symbol": symbol,
        "identity.timestamp": bar_ts.isoformat(),
        "identity.bar_index": int(t),
        "provenance.preregistration_version": V.PREREGISTRATION_VERSION,
        "provenance.feature_versions": dict(V.FEATURE_VERSIONS),
    }

    # ---- Supply / demand
    zones = precomputed_zones if precomputed_zones is not None else sd.detect_zones(symbol, stock_df.iloc[: t + 1])
    sd_ctx = sd.context_at(zones, stock_df, t, planned_risk_unit)
    out.update(sd_ctx)

    # ---- Relative strength (needs SPY closes)
    if spy_df is not None and not spy_df.empty:
        rs_ctx = rs.context_at(
            stock_df.iloc[: t + 1]["close"],
            spy_df["close"] if "close" in spy_df.columns else spy_df.iloc[:, 0],
            bar_ts,
        )
    else:
        rs_ctx = rs._empty_context(reason="no_spy_data")
    out.update(rs_ctx)

    # ---- Market regime (semantic + components + confidence)
    market_ctx = rg.market_context_at(spy_df, bar_ts) if spy_df is not None else {
        "market._feature_version": "v0.3.0",
        "market.spy_regime_semantic": "UNKNOWN+UNKNOWN",
        "market.spy_regime_coarse": "UNKNOWN",
        "market.spy_trend_component": "UNKNOWN",
        "market.spy_risk_component": "UNKNOWN",
        "market.spy_regime_conflict": None,
        "market.spy_regime_confidence": "low",
        "market.spy_regime_availability": False,
    }
    out.update(market_ctx)

    # ---- SMA trend (stock + SPY + derived)
    sma_ctx = smat.context_at(stock_df, spy_df, t, spy_t=bar_ts)
    out.update(sma_ctx)

    # ---- MACD momentum
    mom_ctx = mom.context_at(stock_df, t)
    out.update(mom_ctx)

    # ---- Volatility (BB + TTM + composite label)
    vol_ctx = vol.context_at(stock_df, t)
    for k, v in vol_ctx.items():
        # vol_ctx already carries squeeze fields; do not overwrite feature version
        out[k] = v

    return out
