"""Versions for the research ledger. Bumped only when the math changes.

Purpose: reproducibility of a research run. Every result file carries these
in its manifest so a rerun on the same data + same versions produces the
same numbers, and a change here shows up as a diff in every downstream
report.
"""

PREREGISTRATION_VERSION = "v0.3"
DETECTOR_VERSIONS = {
    "BREAKOUT_INSIDE_DAY_CONTINUATION": "v0.2.1",  # v0.2 fields + planned-price gap fix
}
RESOLVER_VERSION = "v0.2.0"      # WIN/LOSS/AMBIGUOUS/TIMEOUT four-way

FEATURE_VERSIONS = {
    "supply_demand":         "v0.3.0",
    "relative_strength":     "v0.3.0",
    "regime_semantic":       "v0.3.0",   # bump on component exposure
    "sma_trend":             "v0.3.0",
    "momentum_macd":         "v0.3.0",
    "squeeze_ttm":           "v0.3.0",
    "bollinger_extended":    "v0.3.0",
    "volatility_label":      "v0.3.0",
    "levels":                "v0.2.0",
    "features_core":         "v0.2.0",
}
