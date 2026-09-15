# `research/` — setup-context research module

**Read-only.** Does not import from `src/`. `src/` does not import from here.
Nothing in this tree touches production scoring, alerts, entries, ranking
weights, or trade eligibility.

The definitions and thresholds this module uses are locked in
[`PREREGISTRATION.md`](PREREGISTRATION.md). Change one, bump the version
there.

## Layout
```
research/
├── PREREGISTRATION.md    # locked definitions (edit → version bump)
├── README.md             # this file
├── math_utils.py         # BB, ATR, EMA, MACD, fractal pivots — no src/ import
├── features.py           # freeze_at(df, t) → feature dict (lookahead-safe)
├── resolve.py            # +2R-before-−1R walker
├── regime.py             # per-bar SPY regime tag
├── data.py               # Alpaca / yfinance / cached-file bar sources
├── cells.py              # cell (filter) definitions per detector
├── runner.py             # scan × resolve, produce occurrences DataFrame
├── report.py             # stats aggregation + markdown/CSV output
├── cli.py                # entrypoint
├── detectors/
│   ├── _base.py          # Occurrence dataclass, Detector protocol
│   └── breakout_inside_day_continuation.py     # phase 1 — full
│   #  (ASCENDING_COMPRESSION_BREAKOUT, DEMAND_PIVOT_REVERSAL,
│   #   TREND_PULLBACK_CONTINUATION, OUTSIDE_DAY_LEVEL_REVERSAL — TBD)
└── tests/
    ├── test_resolve.py            # +2R-before-−1R walker unit tests
    ├── test_no_lookahead.py       # future-corruption test on features + detector
    └── test_bidc_detector.py      # synthetic-setup sanity check for BIDC
```

## Offline self-test (no network — works in any environment)
```
pip install pytest pandas numpy
pytest research/tests -q
```

## Real backtest run (on the droplet)

1. Fetch bars once into a cache directory (so the whole research is
   reproducible without network dependency later):

    ```python
    # ad-hoc download script (write once, keep in your notes)
    from datetime import date
    from research.data import AlpacaSource   # or YFinanceSource
    from pathlib import Path
    import json

    src = AlpacaSource()  # requires ALPACA_KEY, ALPACA_SECRET env vars
    universe = json.loads(Path("config/universe.json").read_text())
    symbols = sorted({c for sec in universe["sectors"] for c in sec["candidates"]})
    start = date(2020, 1, 1)
    end = date(2026, 1, 1)
    out = Path("data/research_bars")
    out.mkdir(parents=True, exist_ok=True)
    for sym in symbols + ["SPY"]:
        df = src.daily(sym, start, end)
        if not df.empty:
            df.to_parquet(out / f"{sym}.parquet")
    ```

2. Run the detector:

    ```
    python -m research.cli run \
        --detector BREAKOUT_INSIDE_DAY_CONTINUATION \
        --symbols-file config/universe.json \
        --cache-dir data/research_bars \
        --start 2020-01-01 --end 2026-01-01
    ```

3. Results appear under `research/results/breakout_inside_day_continuation_<ts>/`:
    - `stats.md` — human-readable cell table
    - `stats.csv` — same as CSV
    - `occurrences.csv` — every event (symbol × t0), features frozen, outcome
    - `manifest.json` — run params, drop reasons, version

## Interpretation notes (please read before drawing conclusions)

- Every cell is a **filter**, not a score. A cell's row is the subset of
  occurrences satisfying its predicate.
- `lift_vs_parent_pct` compares this cell's win-rate to the named parent's.
  Zero or negative lift with a large n is a genuine "this modifier does not
  add edge" signal — keep it, don't hide it.
- `⚠` = `n < 30`. Do not draw conclusions.
- Same-bar ambiguity in the resolver is **called LOSS** (see
  `PREREGISTRATION.md § Resolution`). This is a conservative choice; on
  extremely-tight-stop setups it will bias against the setup family. If it
  matters, we split a "clean-fill" cell out — do that as a separate
  preregistered analysis, not as a threshold tune.
- The BIDC detector is a proof-of-shape for the runner + report + cells
  pipeline. The other four detectors will follow after phase-1 review.

## What this module deliberately does NOT do

- No composite score combining features.
- No optimization of thresholds to maximize R (or any other metric).
- No wiring to the dashboard, the Telegram bot, or the algo book.
- No promotion of anything to "signal" status.

Every conclusion is meant to survive being sent to another AI or a human
reviewer with the preregistration file attached. Discipline is the point.
