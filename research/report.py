"""Report generation (v0.2).

Primary stats never coerce AMBIGUOUS bars to LOSS. Sensitivity bounds
(conservative / optimistic) are reported alongside. Ambiguous rate and
gap-rates are separate diagnostics.

Layer-2 semantic regime is preserved verbatim on every occurrence and
tabulated per cell. Coarse buckets (BULL_ENV / BEAR_ENV / CHOP) are shown as
supplementary columns.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .cells import Cell


N_WARN = 30
BOOTSTRAP_N = 1000
BOOTSTRAP_CI = 0.95


def _bootstrap_seed(run_id: str, cell_name: str) -> int:
    """Deterministic per-cell seed derived from run_id + cell name."""
    h = hashlib.sha256(f"{run_id}|{cell_name}".encode()).digest()
    return int.from_bytes(h[:4], "big")


def _bootstrap_ci(values: np.ndarray, *, seed: int,
                  stat_fn, n_boot: int = BOOTSTRAP_N,
                  ci: float = BOOTSTRAP_CI) -> tuple[float, float]:
    """Percentile bootstrap CI on `stat_fn(values)`.

    Returns (low, high). NaN pair if n < N_WARN or values is empty.
    """
    values = np.asarray(values, dtype=float)
    values = values[~np.isnan(values)]
    if len(values) < N_WARN:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    stats = np.empty(n_boot)
    n = len(values)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        stats[i] = stat_fn(values[idx])
    lo_q = (1 - ci) / 2
    hi_q = 1 - lo_q
    lo, hi = np.quantile(stats, [lo_q, hi_q])
    return round(float(lo), 3), round(float(hi), 3)


def _features_dict(row: pd.Series) -> dict:
    return {k[len("feat_"):]: v for k, v in row.items() if k.startswith("feat_")}


def _apply_cell(df: pd.DataFrame, cell: Cell) -> pd.DataFrame:
    if df.empty:
        return df
    mask = df.apply(lambda r: bool(cell.predicate(_features_dict(r))), axis=1)
    return df[mask]


def _rate(numer: int, denom: int) -> float:
    return round(100.0 * numer / denom, 2) if denom > 0 else float("nan")


def _mean(x: pd.Series) -> float:
    x = x.dropna()
    if x.empty:
        return float("nan")
    return round(float(x.mean()), 3)


def _median(x: pd.Series) -> float:
    x = x.dropna()
    if x.empty:
        return float("nan")
    return round(float(x.median()), 3)


def _stats_for(sub: pd.DataFrame, *, run_id: str = "unknown",
               cell_name: str = "cell") -> dict:
    n_total = len(sub)
    if n_total == 0:
        return _empty_stats()

    is_clean = sub["feat_entry_gap_flag"] == "clean"
    # gap-through-stop / gap-through-target rates over the whole subset
    n_gap_stop = int((sub["feat_entry_gap_flag"] == "gap_through_stop").sum())
    n_gap_target = int((sub["feat_entry_gap_flag"] == "gap_through_target").sum())
    gap_rate = _rate(n_gap_stop + n_gap_target, n_total)

    # Primary set = clean-gap rows only. Gap rows are excluded from primary.
    primary_set = sub[is_clean]
    n_p = len(primary_set)

    n_win = int((primary_set["outcome"] == "win").sum())
    n_loss = int((primary_set["outcome"] == "loss").sum())
    n_ambig = int((primary_set["outcome"] == "ambiguous").sum())
    n_timeout = int((primary_set["outcome"] == "timeout").sum())
    n_scoreable = n_win + n_loss + n_timeout  # excludes ambiguous

    ambig_rate = _rate(n_ambig, n_p)

    primary_pct = _rate(n_win, n_scoreable)
    conservative_pct = _rate(n_win, n_p)                 # ambig → non-win
    optimistic_pct = _rate(n_win + n_ambig, n_p)         # ambig → win

    # mean_R primary excludes ambiguous (NaN r_multiple → dropna); conservative
    # and optimistic use pre-populated columns from the resolver.
    mean_R_primary = _mean(primary_set["r_multiple"])
    mean_R_conservative = _mean(primary_set["r_multiple_conservative"])
    mean_R_optimistic = _mean(primary_set["r_multiple_optimistic"])
    median_R_primary = _median(primary_set["r_multiple"])
    total_R = float(round(primary_set["r_multiple"].dropna().sum(), 3)) if not primary_set.empty else 0.0

    # ---- Bootstrap CIs (deterministic seed per cell)
    seed = _bootstrap_seed(run_id, cell_name)
    scoreable_r = primary_set.loc[primary_set["outcome"].isin(["win", "loss", "timeout"]), "r_multiple"].to_numpy()
    expectancy_ci_lo, expectancy_ci_hi = _bootstrap_ci(
        scoreable_r, seed=seed, stat_fn=np.mean,
    )
    # Win rate CI uses a 0/1 vector on scoreable rows
    if len(scoreable_r) >= N_WARN:
        wins_vec = np.array(
            [1.0 if o == "win" else 0.0
             for o in primary_set.loc[primary_set["outcome"].isin(["win", "loss", "timeout"]), "outcome"]]
        )
        wr_lo, wr_hi = _bootstrap_ci(
            wins_vec, seed=seed + 1, stat_fn=lambda x: float(x.mean() * 100.0),
        )
    else:
        wr_lo, wr_hi = float("nan"), float("nan")

    # Layer-2 regime split (primary set)
    regime_split_raw = primary_set["regime_semantic"].value_counts().to_dict()
    coarse_split = primary_set["regime_coarse"].value_counts().to_dict()

    return {
        "n_total": n_total,
        "n_primary": n_p,
        "n_win": n_win, "n_loss": n_loss,
        "n_ambiguous": n_ambig, "n_timeout": n_timeout,
        "n_scoreable": n_scoreable,
        "resolved_n": n_scoreable,
        "primary_2R_pct": primary_pct,
        "conservative_2R_pct": conservative_pct,
        "optimistic_2R_pct": optimistic_pct,
        "ambiguous_rate": ambig_rate,
        "gap_rate": gap_rate,
        "gap_through_stop_rate": _rate(n_gap_stop, n_total),
        "gap_through_target_rate": _rate(n_gap_target, n_total),
        "expectancy_R": mean_R_primary,
        "mean_R_primary": mean_R_primary,
        "mean_R_conservative": mean_R_conservative,
        "mean_R_optimistic": mean_R_optimistic,
        "median_R": median_R_primary,
        "median_R_primary": median_R_primary,
        "total_R": total_R,
        "expectancy_R_ci_low": expectancy_ci_lo,
        "expectancy_R_ci_high": expectancy_ci_hi,
        "win_rate_ci_low": wr_lo,
        "win_rate_ci_high": wr_hi,
        "mean_MAE": _mean(primary_set["mae_R"]),
        "mean_MFE": _mean(primary_set["mfe_R"]),
        "mean_bars": _mean(primary_set["bars_to_resolve"].astype(float)),
        "regime_l2_split": regime_split_raw,
        "regime_coarse_split": coarse_split,
    }


def _empty_stats() -> dict:
    return {
        "n_total": 0, "n_primary": 0,
        "n_win": 0, "n_loss": 0, "n_ambiguous": 0, "n_timeout": 0, "n_scoreable": 0,
        "resolved_n": 0,
        "primary_2R_pct": float("nan"),
        "conservative_2R_pct": float("nan"),
        "optimistic_2R_pct": float("nan"),
        "ambiguous_rate": float("nan"),
        "gap_rate": float("nan"),
        "gap_through_stop_rate": float("nan"),
        "gap_through_target_rate": float("nan"),
        "expectancy_R": float("nan"),
        "mean_R_primary": float("nan"),
        "mean_R_conservative": float("nan"),
        "mean_R_optimistic": float("nan"),
        "median_R": float("nan"),
        "median_R_primary": float("nan"),
        "total_R": 0.0,
        "expectancy_R_ci_low": float("nan"),
        "expectancy_R_ci_high": float("nan"),
        "win_rate_ci_low": float("nan"),
        "win_rate_ci_high": float("nan"),
        "mean_MAE": float("nan"),
        "mean_MFE": float("nan"),
        "mean_bars": float("nan"),
        "regime_l2_split": {},
        "regime_coarse_split": {},
    }


def build_stats(occ: pd.DataFrame, cells: list[Cell], *,
                run_id: str = "unknown") -> pd.DataFrame:
    """One row per cell with all metrics + lift_vs_parent + bootstrap CIs."""
    stats: dict[str, dict] = {}
    for cell in cells:
        sub = _apply_cell(occ, cell)
        s = _stats_for(sub, run_id=run_id, cell_name=cell.name)
        stats[cell.name] = s

    rows = []
    for cell in cells:
        s = dict(stats[cell.name])
        s["cell"] = cell.name
        s["parent"] = cell.parent or "-"
        s["redundant_by_construction"] = bool(cell.redundant_by_construction)
        s["families"] = ",".join(cell.families) if cell.families else ""
        if cell.parent and cell.parent in stats:
            ps = stats[cell.parent]
            if _finite(s["primary_2R_pct"]) and _finite(ps["primary_2R_pct"]):
                s["lift_vs_parent_pct"] = round(s["primary_2R_pct"] - ps["primary_2R_pct"], 2)
            else:
                s["lift_vs_parent_pct"] = float("nan")
        else:
            s["lift_vs_parent_pct"] = float("nan")
        s["warn_low_n"] = "⚠" if s["n_scoreable"] < N_WARN else ""
        rows.append(s)

    col_order = [
        "cell", "parent", "families", "redundant_by_construction",
        "n_total", "n_primary",
        "n_win", "n_loss", "n_ambiguous", "n_timeout", "n_scoreable", "resolved_n",
        "primary_2R_pct", "conservative_2R_pct", "optimistic_2R_pct",
        "win_rate_ci_low", "win_rate_ci_high",
        "ambiguous_rate", "gap_rate",
        "gap_through_stop_rate", "gap_through_target_rate",
        "expectancy_R", "expectancy_R_ci_low", "expectancy_R_ci_high",
        "mean_R_primary", "mean_R_conservative", "mean_R_optimistic",
        "median_R", "median_R_primary", "total_R",
        "mean_MAE", "mean_MFE", "mean_bars",
        "lift_vs_parent_pct", "warn_low_n",
        "regime_l2_split", "regime_coarse_split",
    ]
    df = pd.DataFrame(rows)
    df["regime_l2_split"] = df["regime_l2_split"].apply(json.dumps)
    df["regime_coarse_split"] = df["regime_coarse_split"].apply(json.dumps)
    return df[col_order]


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not (isinstance(x, float) and math.isnan(x))


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
        f"# {name} — research results (preregistration {manifest.get('preregistration_version','?')})",
        "",
        f"- git_commit: `{manifest.get('git_commit', 'unknown')}`",
        f"- run_id: `{manifest.get('run_id', 'unknown')}`",
        f"- detector_version: {manifest.get('detector_version', '?')}",
        f"- resolver_version: {manifest.get('resolver_version', '?')}",
        f"- feature_versions: {json.dumps(manifest.get('feature_versions', {}))}",
        f"- dataset_hash: `{manifest.get('dataset_hash', '?')[:16]}…`",
        f"- config_hash:  `{manifest.get('config_hash', '?')[:16]}…`",
        f"- Symbols requested: {manifest.get('n_symbols_requested', 0)}",
        f"- Symbols with data: {manifest.get('n_symbols_ok', 0)}",
        f"- Occurrences: {manifest.get('n_occurrences', 0)}",
        f"- Resolution window: {manifest.get('max_bars_to_resolve', 30)} bars",
        f"- Range: {manifest.get('start')} → {manifest.get('end')}",
        f"- Drop reasons: {json.dumps(manifest.get('drop_reasons', {}))}",
        "",
        "## Cells",
        "",
        "Every cell renders — including n=0. AMBIGUOUS bars are NOT coerced. "
        "`primary_2R_pct` = wins ÷ scoreable (excludes ambiguous). "
        "`conservative_2R_pct` = wins ÷ primary_total (ambig → non-win). "
        "`optimistic_2R_pct` = (wins + ambig) ÷ primary_total. "
        "Gap-through-stop and gap-through-target rows are excluded from the "
        "primary set and reported as diagnostic rates.",
        "",
    ]
    cols = [
        "cell", "n_primary", "n_ambiguous",
        "primary_2R_pct", "conservative_2R_pct", "optimistic_2R_pct",
        "ambiguous_rate",
        "gap_through_stop_rate", "gap_through_target_rate",
        "mean_R_primary", "lift_vs_parent_pct", "warn_low_n",
    ]
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("|" + "|".join(["---"] * len(cols)) + "|")
    for _, row in stats.iterrows():
        vals = []
        for c in cols:
            v = row[c]
            if isinstance(v, float) and math.isnan(v):
                vals.append("—")
            else:
                vals.append(str(v))
        lines.append("| " + " | ".join(vals) + " |")
    lines.append("")
    lines.append("⚠ = n_scoreable < 30 (sample size warning).")
    lines.append("")
    lines.append("Full Layer-2 regime split per cell is in `stats.csv` under "
                 "`regime_l2_split` (JSON dict). Coarse buckets in `regime_coarse_split`.")
    return "\n".join(lines)
