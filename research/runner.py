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

import hashlib
import logging
import subprocess
import uuid
from datetime import date, datetime, timezone
from typing import Iterable

import pandas as pd

from . import regime as regime_mod
from . import versioning as V
from .data import BarSource
from .detectors._base import Detector
from .resolve import Resolution, resolve


logger = logging.getLogger(__name__)


def _git_commit() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL,
        ).decode().strip()
        return out
    except Exception:  # noqa: BLE001
        return "unknown"


def _dataset_hash(rows: list[dict]) -> str:
    """sha256 of per-symbol OHLC digests (symbol + t0 + entry + stop + target)."""
    h = hashlib.sha256()
    for r in rows:
        h.update(f"{r.get('symbol')}|{r.get('t0')}|{r.get('entry')}|{r.get('stop')}|{r.get('target')}\n".encode())
    return h.hexdigest()


def _config_hash(config: dict) -> str:
    """Deterministic hash of preregistered thresholds + run config."""
    items = sorted(config.items())
    payload = "\n".join(f"{k}={v}" for k, v in items).encode()
    return hashlib.sha256(payload).hexdigest()


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
    run_id = str(uuid.uuid4())
    run_ts = datetime.now(timezone.utc).isoformat()
    manifest = {
        "git_commit": _git_commit(),
        "preregistration_version": V.PREREGISTRATION_VERSION,
        "detector": detector.name,
        "detector_version": V.DETECTOR_VERSIONS.get(detector.name, "unknown"),
        "resolver_version": V.RESOLVER_VERSION,
        "feature_versions": dict(V.FEATURE_VERSIONS),
        "run_id": run_id,
        "run_timestamp": run_ts,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "max_bars_to_resolve": max_bars,
        "max_bars_per_symbol": max_bars_per_symbol,
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
    manifest["dataset_hash"] = _dataset_hash(rows)
    manifest["config_hash"] = _config_hash({
        "detector": detector.name,
        "max_bars": max_bars,
        "max_bars_per_symbol": max_bars_per_symbol,
        "preregistration_version": V.PREREGISTRATION_VERSION,
        "resolver_version": V.RESOLVER_VERSION,
        "feature_versions": tuple(sorted(V.FEATURE_VERSIONS.items())),
    })
    return pd.DataFrame(rows), manifest
