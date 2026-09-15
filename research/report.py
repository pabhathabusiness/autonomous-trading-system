"""Report generation.

Takes the occurrences DataFrame + a list of Cells and produces:
  - stats DataFrame with cell x metric grid
  - occurrences.csv (long-form, one row per event)
  - manifest.json
  - stats.md (human-readable)
  - stats.csv

Nothing here decides "is this cell good enough" — we render the numbers and
warn on sample size. Interpretation is the user's job.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .cells import Cell


N_WARN = 30


def _features_dict(row: pd.Series) -> dict:
    """Un-prefix `feat_*` columns back into a dict for predicate access."""
    return {k[len("feat_"):]: v for k, v in row.items() if k.startswith("feat_")}


def _apply_cell(df: pd.DataFrame, cell: Cell) -> pd.DataFrame:
    if df.empty:
        return df
    mask = df.apply(lambda r: bool(cell.predicate(_features_dict(r))), axis=1)
    return df[mask]


def _stats_for(sub: pd.DataFrame) -> dict:
    if sub.empty:
        return {
            "n": 0, "plus2R_pct": np.nan, "mean_R": np.nan, "median_R": np.nan,
            "mean_MAE": np.nan, "mean_MFE": np.nan, "mean_bars": np.nan,
            "n_BULL": 0, "n_BEAR": 0, "n_NEUT": 0, "n_UNK": 0,
        }
    wins = (sub["outcome"] == "win").sum()
    n = len(sub)
    return {
        "n": n,
        "plus2R_pct": round(100.0 * wins / n, 2),
        "mean_R": round(float(sub["r_multiple"].mean()), 3),
        "median_R": round(float(sub["r_multiple"].median()), 3),
        "mean_MAE": round(float(sub["mae_R"].mean()), 3),
        "mean_MFE": round(float(sub["mfe_R"].mean()), 3),
        "mean_bars": round(float(sub["bars_to_resolve"].mean()), 2),
        "n_BULL": int((sub["regime"] == "BULL").sum()),
        "n_BEAR": int((sub["regime"] == "BEAR").sum()),
        "n_NEUT": int((sub["regime"] == "NEUTRAL").sum()),
        "n_UNK":  int((sub["regime"] == "UNKNOWN").sum()),
    }


def build_stats(occ: pd.DataFrame, cells: list[Cell]) -> pd.DataFrame:
    """Returns a DataFrame indexed by cell name with metric columns + a
    `lift_vs_parent_pct` column (relative to the referenced parent cell)."""
    rows = []
    subs: dict[str, pd.DataFrame] = {}
    stats: dict[str, dict] = {}
    for cell in cells:
        sub = _apply_cell(occ, cell)
        subs[cell.name] = sub
        s = _stats_for(sub)
        stats[cell.name] = s

    for cell in cells:
        s = dict(stats[cell.name])
        s["cell"] = cell.name
        s["parent"] = cell.parent or "-"
        if cell.parent and cell.parent in stats:
            ps = stats[cell.parent]
            if pd.notna(s["plus2R_pct"]) and pd.notna(ps["plus2R_pct"]):
                s["lift_vs_parent_pct"] = round(s["plus2R_pct"] - ps["plus2R_pct"], 2)
            else:
                s["lift_vs_parent_pct"] = np.nan
        else:
            s["lift_vs_parent_pct"] = np.nan
        s["warn_low_n"] = "⚠" if s["n"] < N_WARN else ""
        rows.append(s)

    cols = ["cell", "parent", "n", "plus2R_pct", "lift_vs_parent_pct",
            "mean_R", "median_R", "mean_MAE", "mean_MFE", "mean_bars",
            "n_BULL", "n_BEAR", "n_NEUT", "n_UNK", "warn_low_n"]
    return pd.DataFrame(rows)[cols]


def write_results(
    out_dir: Path, detector_name: str,
    occurrences: pd.DataFrame, stats: pd.DataFrame, manifest: dict,
) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    run_dir = out_dir / f"{detector_name.lower()}_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)

    occurrences.to_csv(run_dir / "occurrences.csv", index=False)
    stats.to_csv(run_dir / "stats.csv", index=False)
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    (run_dir / "stats.md").write_text(_stats_to_md(detector_name, stats, manifest))
    return run_dir


def _stats_to_md(name: str, stats: pd.DataFrame, manifest: dict) -> str:
    lines = [
        f"# {name} — research results",
        "",
        f"- Symbols requested: {manifest.get('n_symbols_requested', 0)}",
        f"- Symbols with data: {manifest.get('n_symbols_ok', 0)}",
        f"- Occurrences: {manifest.get('n_occurrences', 0)}",
        f"- Resolution window: {manifest.get('max_bars_to_resolve', 30)} bars",
        f"- Range: {manifest.get('start')} → {manifest.get('end')}",
        "",
        "Drop reasons: " + (json.dumps(manifest.get("drop_reasons", {})) or "none"),
        "",
        "## Cells",
        "",
    ]
    # Table
    cols = ["cell", "n", "plus2R_pct", "lift_vs_parent_pct", "mean_R", "median_R",
            "mean_MAE", "mean_MFE", "mean_bars", "n_BULL", "n_BEAR", "n_NEUT", "warn_low_n"]
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("|" + "|".join(["---"] * len(cols)) + "|")
    for _, row in stats.iterrows():
        vals = []
        for c in cols:
            v = row[c]
            if isinstance(v, float) and pd.isna(v):
                vals.append("—")
            else:
                vals.append(str(v))
        lines.append("| " + " | ".join(vals) + " |")
    lines.append("")
    lines.append("⚠ = n < 30 (sample size warning).")
    lines.append("")
    lines.append("Every cell above rendered EVEN when n=0. Failed / null "
                 "results are NOT hidden. Broad preregistered thresholds only.")
    return "\n".join(lines)
