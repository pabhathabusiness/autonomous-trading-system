"""Backtest runner (v0.2).

For each symbol × detector:
  1. Fetch bars from BarSource.
  2. detector.scan(symbol, df) → list[Occurrence]  (features frozen).
  3. For each Occurrence:
       a. Slice bars_fwd from t0 + entry_bar_offset.
       b. Classify entry gap (informational; the flag is already on the
          occurrence but we re-derive here for defense).
       c. Call resolve.resolve() → Resolution with four-way outcome.
       d. Tag Layer-2 semantic regime at t0 from SPY.
       e. Append row.

No I/O. Caller writes the DataFrame via report.write_results.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Iterable

import pandas as pd

from . import regime as regime_mod
from .data import BarSource
from .detectors._base import Detector
from .resolve import Resolution, resolve


logger = logging.getLogger(__name__)


def run_detector(
    detector: Detector,
    symbols: Iterable[str],
    source: BarSource,
    start: date,
    end: date,
    max_bars: int = 30,
    spy_source: BarSource | None = None,
    max_bars_per_symbol: int = 1500,
) -> tuple[pd.DataFrame, dict]:
    manifest = {
        "preregistration_version": "v0.2",
        "detector": detector.name,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "max_bars_to_resolve": max_bars,
        "n_symbols_requested": 0,
        "n_symbols_ok": 0,
        "drop_reasons": {},
    }

    spy_df = pd.DataFrame()
    if spy_source is not None:
        spy_df = spy_source.daily("SPY", start, end)
        if spy_df.empty:
            manifest["drop_reasons"]["spy_regime_unavailable"] = 1

    rows: list[dict] = []
    seen = 0
    for symbol in symbols:
        seen += 1
        df = source.daily(symbol, start, end)
        if df.empty:
            manifest["drop_reasons"].setdefault("no_bars", 0)
            manifest["drop_reasons"]["no_bars"] += 1
            continue
        df = df.tail(max_bars_per_symbol)
        try:
            occs = detector.scan(symbol, df)
        except Exception as e:  # noqa: BLE001
            key = f"scan_error:{type(e).__name__}"
            manifest["drop_reasons"].setdefault(key, 0)
            manifest["drop_reasons"][key] += 1
            logger.warning("%s scan error: %s", symbol, e)
            continue

        manifest["n_symbols_ok"] += 1
        for occ in occs:
            try:
                t0_iloc = df.index.get_loc(occ.t0)
            except KeyError:
                continue
            first_fwd = t0_iloc + occ.entry_bar_offset
            if first_fwd >= len(df):
                continue
            bars_fwd = df.iloc[first_fwd:]

            res: Resolution = resolve(
                entry=occ.entry, stop=occ.stop, target=occ.target,
                side=occ.side, bars_fwd=bars_fwd, max_bars=max_bars,
            )

            if spy_df.empty:
                regime = regime_mod.SemanticRegime("UNKNOWN", "UNKNOWN")
            else:
                regime = regime_mod.semantic_regime_at(spy_df, occ.t0)

            row = {
                "symbol": occ.symbol,
                "t0": occ.t0,
                "side": occ.side,
                "entry": occ.entry,
                "stop": occ.stop,
                "target": occ.target,
                "outcome": res.outcome,
                "r_multiple": res.r_multiple,
                "r_multiple_conservative": res.r_multiple_conservative,
                "r_multiple_optimistic": res.r_multiple_optimistic,
                "bars_to_resolve": res.bars_to_resolve,
                "mae_R": res.mae,
                "mfe_R": res.mfe,
                "regime_semantic": regime.label,
                "regime_coarse": regime.coarse,
            }
            for k, v in occ.features.items():
                row[f"feat_{k}"] = v
            rows.append(row)

    manifest["n_symbols_requested"] = seen
    manifest["n_occurrences"] = len(rows)
    return pd.DataFrame(rows), manifest
