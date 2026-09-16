"""Relative strength vs SPY — daily-first, causal.

Alignment: `pd.merge_asof(direction='backward', tolerance=1 day)` on the
stock and SPY close series. No forward-fill through missing bars — if SPY
has a gap on the stock's bar t, we drop that pair rather than pretend SPY
traded.

Minimum-observation rules per PREREGISTRATION.md § "Minimum observation
rules (v0.3)":
  - rs_spy_Nd:                      ≥ N + 1 aligned bars
  - rs_class:                       requires rs_spy_20d
  - rs_during_spy_weakness_*:       ≥ 10 qualifying weakness bars in trailing 60
  - rs_during_spy_strength_*:       ≥ 10 qualifying strength bars in trailing 60
  - stock_hh_spy_no_hh / structural: ≥ structure_lookback + 2 aligned bars

Below the minimum, a field returns `None` (numeric) or `"UNAVAILABLE"`
(label), and an `_availability` sibling flag is False. Neither value may
be coerced to a neutral / zero / False default downstream.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


FEATURE_VERSION = "v0.3.0"

# Preregistered class thresholds on rs_spy_20d (fractional returns).
_RS_OUTPERFORM_TH = 0.05
_RS_UNDERPERFORM_TH = -0.02

# Preregistered minimum qualifying bars for regime-conditioned RS.
_MIN_REGIME_BARS = 10
# Preregistered SPY-regime window (trailing bars used for the count).
_REGIME_LOOKBACK = 60


def _align_backward(stock_closes: pd.Series, spy_closes: pd.Series,
                    tolerance_days: int = 1) -> pd.DataFrame:
    """DataFrame indexed by stock's timestamps with columns ['stock', 'spy'].
    SPY is matched via backward asof with a 1-day tolerance; stock bars where
    no SPY bar is within tolerance become NaN and are dropped by callers.
    """
    st = stock_closes.rename("stock").to_frame().sort_index()
    sp = spy_closes.rename("spy").to_frame().sort_index()
    if not isinstance(st.index, pd.DatetimeIndex):
        st.index = pd.to_datetime(st.index, utc=True, errors="coerce")
    if not isinstance(sp.index, pd.DatetimeIndex):
        sp.index = pd.to_datetime(sp.index, utc=True, errors="coerce")
    st = st[st.index.notna()]
    sp = sp[sp.index.notna()]
    joined = pd.merge_asof(
        st.reset_index().rename(columns={"index": "ts"}),
        sp.reset_index().rename(columns={"index": "ts"}),
        on="ts",
        direction="backward",
        tolerance=pd.Timedelta(days=tolerance_days),
    ).set_index("ts")
    return joined


def _return(series: pd.Series, periods: int) -> float:
    if len(series) <= periods:
        return float("nan")
    start, end = series.iloc[-periods - 1], series.iloc[-1]
    if not (pd.notna(start) and pd.notna(end)) or start <= 0:
        return float("nan")
    return float(end / start - 1.0)


def context_at(stock_closes: pd.Series, spy_closes: pd.Series, t: pd.Timestamp,
               *, weakness_lookback: int = _REGIME_LOOKBACK,
               structure_lookback: int = 20) -> dict:
    """Compute RS context for the stock at bar `t`. Consults only stock and
    SPY closes with index ≤ t (aligned)."""
    aligned = _align_backward(stock_closes, spy_closes)
    up_to = aligned[aligned.index <= t]
    if up_to.empty:
        return _empty_context(reason="no_aligned_history")

    # Drop rows where SPY couldn't be matched — never forward-fill.
    up_to = up_to.dropna(subset=["stock", "spy"])
    if len(up_to) < 2:
        return _empty_context(reason="insufficient_aligned_history")

    stock = up_to["stock"]
    spy = up_to["spy"]

    out: dict = {
        "relative_strength._feature_version": FEATURE_VERSION,
        "relative_strength._source_timeframe": "1d",
        "relative_strength._source_data_end": stock.index[-1].isoformat(),
        "relative_strength._known_at": stock.index[-1].isoformat(),
        "relative_strength._n_aligned_bars": int(len(up_to)),
    }

    # ---- multi-lookback returns (per-window availability)
    ret_windows = {"1d": 1, "5d": 5, "10d": 10, "20d": 20}
    for label, n in ret_windows.items():
        available = len(up_to) >= n + 1
        sr = _return(stock, n) if available else float("nan")
        pr = _return(spy, n) if available else float("nan")
        out[f"relative_strength.stock_return_{label}"] = _num(sr)
        out[f"relative_strength.spy_return_{label}"] = _num(pr)
        rs = float(sr - pr) if (np.isfinite(sr) and np.isfinite(pr)) else float("nan")
        out[f"relative_strength.rs_spy_{label}"] = _num(rs)
        out[f"relative_strength.rs_spy_{label}_availability"] = bool(np.isfinite(rs))

    rs_1 = out.get("relative_strength.rs_spy_1d")
    rs_5 = out.get("relative_strength.rs_spy_5d")
    rs_20 = out.get("relative_strength.rs_spy_20d")

    slope_short = ((rs_5 - rs_1) / 4) if (rs_5 is not None and rs_1 is not None) else None
    slope_medium = ((rs_20 - rs_5) / 15) if (rs_20 is not None and rs_5 is not None) else None
    accel = ((slope_short - slope_medium)
             if (slope_short is not None and slope_medium is not None) else None)
    out["relative_strength.rs_slope_short"] = slope_short
    out["relative_strength.rs_slope_medium"] = slope_medium
    out["relative_strength.rs_acceleration"] = accel

    # ---- rs_class from rs_spy_20d (preregistered thresholds)
    if rs_20 is None:
        rs_class = "UNAVAILABLE"
        rs_class_available = False
    elif rs_20 >= _RS_OUTPERFORM_TH:
        rs_class = "OUTPERFORMING"
        rs_class_available = True
    elif rs_20 <= _RS_UNDERPERFORM_TH:
        rs_class = "UNDERPERFORMING"
        rs_class_available = True
    else:
        rs_class = "NEUTRAL"
        rs_class_available = True
    out["relative_strength.rs_class"] = rs_class
    out["relative_strength.rs_class_availability"] = rs_class_available

    # ---- RS during SPY weakness / strength (trailing window)
    tail = up_to.tail(weakness_lookback + 1)
    if len(tail) >= 2:
        stock_r = tail["stock"].pct_change().dropna()
        spy_r = tail["spy"].pct_change().dropna()
        common = stock_r.index.intersection(spy_r.index)
        sr_series = stock_r.loc[common]
        pr_series = spy_r.loc[common]

        weakness_mask = pr_series < 0
        strength_mask = pr_series > 0

        out.update(_rs_during_regime(sr_series, pr_series, weakness_mask, "weakness"))
        out.update(_rs_during_regime(sr_series, pr_series, strength_mask, "strength"))
    else:
        out.update(_regime_unavailable("weakness"))
        out.update(_regime_unavailable("strength"))

    # ---- structural divergence booleans (trailing 20 bars)
    if len(up_to) >= structure_lookback + 2:
        w = up_to.tail(structure_lookback + 1)
        stock_max_prev = float(w["stock"].iloc[:-1].max())
        spy_max_prev = float(w["spy"].iloc[:-1].max())
        stock_min_prev = float(w["stock"].iloc[:-1].min())
        spy_min_prev = float(w["spy"].iloc[:-1].min())
        stock_t = float(w["stock"].iloc[-1])
        spy_t = float(w["spy"].iloc[-1])

        out["relative_strength.stock_hh_spy_no_hh"] = bool(stock_t > stock_max_prev and spy_t <= spy_max_prev)
        out["relative_strength.stock_hl_spy_ll"] = bool(stock_t > stock_min_prev and spy_t < spy_min_prev)
        out["relative_strength.stock_holds_low_spy_breaks"] = bool(stock_t > stock_min_prev and spy_t < spy_min_prev)
        out["relative_strength.stock_breaks_high_spy_does_not"] = bool(stock_t > stock_max_prev and spy_t < spy_max_prev)
        out["relative_strength.structural_divergence_availability"] = True
    else:
        for k in ("stock_hh_spy_no_hh", "stock_hl_spy_ll",
                  "stock_holds_low_spy_breaks", "stock_breaks_high_spy_does_not"):
            out[f"relative_strength.{k}"] = None
        out["relative_strength.structural_divergence_availability"] = False

    return out


def _rs_during_regime(stock_r: pd.Series, spy_r: pd.Series, mask: pd.Series, label: str) -> dict:
    """Compute cum return + fractions on bars where `mask` is True.

    Returns UNAVAILABLE (None + availability=False) when the number of
    qualifying bars is below the preregistered minimum (`_MIN_REGIME_BARS`).
    """
    key_prefix = f"relative_strength.rs_during_spy_{label}"
    sub_s = stock_r[mask]
    sub_p = spy_r[mask]
    n = int(len(sub_s))

    if n < _MIN_REGIME_BARS:
        return _regime_unavailable(label, n=n)

    stock_cum = float((1 + sub_s).prod() - 1)
    spy_cum = float((1 + sub_p).prod() - 1)
    out = {
        f"{key_prefix}_stock_cum": stock_cum,
        f"{key_prefix}_spy_cum": spy_cum,
        f"{key_prefix}_diff": stock_cum - spy_cum,
        f"{key_prefix}_n_bars": n,
        f"{key_prefix}_availability": True,
    }
    if label == "weakness":
        out[f"{key_prefix}_frac_outperformed"] = float((sub_s > sub_p).mean())
        out[f"{key_prefix}_frac_stock_positive"] = float((sub_s > 0).mean())
        cum = (1 + sub_s).cumprod()
        rolling_peak = cum.cummax()
        dd = (cum / rolling_peak - 1).min()
        out[f"{key_prefix}_stock_max_dd"] = float(dd) if pd.notna(dd) else None
    else:  # strength
        out[f"{key_prefix}_frac_underperformed"] = float((sub_s < sub_p).mean())
        out[f"{key_prefix}_frac_stock_negative"] = float((sub_s < 0).mean())
        cum = (1 + sub_s).cumprod()
        rolling_trough = cum.cummin()
        ru = (cum / rolling_trough - 1).max()
        out[f"{key_prefix}_stock_max_ru"] = float(ru) if pd.notna(ru) else None
    return out


def _regime_unavailable(label: str, *, n: int = 0) -> dict:
    """UNAVAILABLE payload for rs_during_spy_{label}_* fields."""
    key_prefix = f"relative_strength.rs_during_spy_{label}"
    empty = {
        f"{key_prefix}_stock_cum": None,
        f"{key_prefix}_spy_cum": None,
        f"{key_prefix}_diff": None,
        f"{key_prefix}_n_bars": int(n),
        f"{key_prefix}_availability": False,
    }
    if label == "weakness":
        empty[f"{key_prefix}_frac_outperformed"] = None
        empty[f"{key_prefix}_frac_stock_positive"] = None
        empty[f"{key_prefix}_stock_max_dd"] = None
    else:
        empty[f"{key_prefix}_frac_underperformed"] = None
        empty[f"{key_prefix}_frac_stock_negative"] = None
        empty[f"{key_prefix}_stock_max_ru"] = None
    return empty


def _num(x: float) -> float | None:
    return float(x) if np.isfinite(x) else None


def _empty_context(reason: str | None = None) -> dict:
    out = {
        "relative_strength._feature_version": FEATURE_VERSION,
        "relative_strength._source_timeframe": "1d",
        "relative_strength.rs_class": "UNAVAILABLE",
        "relative_strength.rs_class_availability": False,
    }
    if reason:
        out["relative_strength._reason"] = reason
    return out
