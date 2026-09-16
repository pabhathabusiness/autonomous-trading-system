"""Layer-2 semantic regime tests.

Full state is stored on every occurrence; coarse buckets are report-only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.regime import (
    SemanticRegime, _risk_state, _trend_state, semantic_regime_at,
    semantic_regime_series,
)


def _spy_df(closes: list[float]):
    n = len(closes)
    df = pd.DataFrame(
        {"open": closes, "high": [c + 1 for c in closes],
         "low": [c - 1 for c in closes], "close": closes,
         "volume": [1_000_000] * n},
        index=pd.date_range("2023-01-01", periods=n, freq="D"),
    )
    return df


def test_strong_uptrend_detected_on_clear_uptrend():
    closes = list(np.linspace(80, 120, 100))
    df = _spy_df(closes)
    assert _trend_state(df["close"]) in ("STRONG_UPTREND", "UPTREND")


def test_downtrend_detected_on_clear_downtrend():
    closes = list(np.linspace(120, 80, 100))
    df = _spy_df(closes)
    assert _trend_state(df["close"]) in ("STRONG_DOWNTREND", "DOWNTREND")


def test_sideways_when_flat():
    closes = list(100 + 0.5 * np.sin(np.linspace(0, 6, 100)))
    df = _spy_df(closes)
    assert _trend_state(df["close"]) == "SIDEWAYS"


def test_regime_label_and_coarse_available():
    r = SemanticRegime("STRONG_UPTREND", "RISK_ON")
    assert r.label == "STRONG_UPTREND+RISK_ON"
    assert r.coarse == "BULL_ENV"

    r2 = SemanticRegime("SIDEWAYS", "RISK_NEUTRAL")
    assert r2.coarse == "CHOP"


def test_semantic_regime_at_timestamp():
    closes = list(np.linspace(80, 120, 100))
    df = _spy_df(closes)
    r = semantic_regime_at(df, df.index[-1])
    assert r.trend in ("UPTREND", "STRONG_UPTREND")
    # Full label always available, never coerced to a coarse label
    assert "+" in r.label


def test_full_state_preserved_never_replaced_by_coarse():
    # SIDEWAYS+RISK_OFF is CHOP under coarse; the FULL label must still be exact.
    r = SemanticRegime("SIDEWAYS", "RISK_OFF")
    assert r.label == "SIDEWAYS+RISK_OFF"       # full state
    assert r.coarse == "CHOP"                    # coarse bucket
    # coarse should not overwrite label:
    assert r.label != r.coarse


def test_unknown_when_insufficient_history():
    df = _spy_df([100.0, 101.0])
    r = semantic_regime_at(df, df.index[-1])
    assert r.label == "UNKNOWN+UNKNOWN"
    assert r.coarse == "UNKNOWN"


def test_series_produces_label_per_bar():
    closes = list(np.linspace(80, 120, 100))
    df = _spy_df(closes)
    s = semantic_regime_series(df)
    assert len(s) == len(df)
    # No coerced empty strings; every label has trend+risk shape
    assert all("+" in v for v in s.values)
