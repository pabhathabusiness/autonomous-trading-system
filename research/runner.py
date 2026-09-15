"""Backtest runner.

For each symbol × detector:
  1. Fetch bars from BarSource
  2. detector.scan(symbol, df) → list[Occurrence]  (features already frozen)
  3. For each Occurrence, extract bars_fwd (from entry_bar_offset onward)
     and pass to resolve.resolve() → Resolution
  4. Tag regime at t0 using SPY closes
  5. Append full row to occurrences DataFrame

No I/O. The caller decides what to do with the returned DataFrame
(runner.report writes the stats).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Iterable

import pandas as pd

from . import regime as regime_mod
from .data import BarSource
from .detectors._base import Detector
from .resolve import resolve


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
    """Returns (occurrences_df, manifest_dict).

    manifest carries drop reasons and run metadata for the results directory.
    """
    manifest = {
        "detector": detector.name,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "max_bars_to_resolve": max_bars,
        "n_symbols_requested": 0,
        "n_symbols_ok": 0,
        "drop_reasons": {},
    }

    # SPY for regime tagging
    spy_closes = pd.Series(dtype=float)
    if spy_source is not None:
        spy_df = spy_source.daily("SPY", start, end)
        if not spy_df.empty:
            spy_closes = spy_df["close"]
        else:
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
        except Exception as e:  # noqa: BLE001 — research code, log & continue
            manifest["drop_reasons"].setdefault(f"scan_error:{type(e).__name__}", 0)
            manifest["drop_reasons"][f"scan_error:{type(e).__name__}"] += 1
            logger.warning("%s scan error: %s", symbol, e)
            continue

        manifest["n_symbols_ok"] += 1
        for occ in occs:
            # bars_fwd starts at entry_bar_offset from t0
            t0_iloc = df.index.get_loc(occ.t0)
            first_fwd = t0_iloc + occ.entry_bar_offset
            if first_fwd >= len(df):
                continue  # no forward bars
            bars_fwd = df.iloc[first_fwd:]
            res = resolve(
                entry=occ.entry, stop=occ.stop, target=occ.target,
                side=occ.side, bars_fwd=bars_fwd, max_bars=max_bars,
            )
            regime_tag = regime_mod.tag_at(spy_closes, occ.t0) if len(spy_closes) else "UNKNOWN"
            row = {
                "symbol": occ.symbol,
                "t0": occ.t0,
                "side": occ.side,
                "entry": occ.entry,
                "stop": occ.stop,
                "target": occ.target,
                "outcome": res.outcome,
                "r_multiple": res.r_multiple,
                "bars_to_resolve": res.bars_to_resolve,
                "mae_R": res.mae,
                "mfe_R": res.mfe,
                "regime": regime_tag,
            }
            # Flatten features into row for cell predicate access.
            # Prefix guards against collision with the fixed columns above.
            for k, v in occ.features.items():
                row[f"feat_{k}"] = v
            rows.append(row)

    manifest["n_symbols_requested"] = seen
    manifest["n_occurrences"] = len(rows)
    return pd.DataFrame(rows), manifest
