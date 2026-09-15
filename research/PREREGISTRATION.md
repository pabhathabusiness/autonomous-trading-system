# PREREGISTRATION — Setup Context Research

**Locked before any backtest runs.** Any change to a definition below is a version bump
in this file with a timestamp — no silent retuning.

## Scope
- Read-only research. No production scoring/alerts/ranking/eligibility changes.
- Every modifier reported as its own cell with lift vs parent. **No composite score.**
- Preregistered, broad, interpretable thresholds. **No optimization for R.**
- Preserve failed/null results. Every cell renders even at n < min.

## Universe & timeframe (phase 1)
- **Universe**: dedup of `config/universe.json` candidate lists (~800 US-listed symbols).
- **Timeframe**: daily bars (`1d`). Intraday (`1h`) is a phase-2 addition.
- **History**: 2020-01-01 through T minus 5 days. Cap at 1500 bars/symbol.

## Data source
- Alpaca `bars` batched (primary). yfinance daily as fallback per symbol.
- On both-fail, symbol dropped; drop reason logged; drop count reported.

## Resolution — the +2R-before-−1R framework
For each Occurrence at bar `t0`:

```
long:  E = entry, S = stop (S < E), T = E + 2·(E − S)   # target = +2R
short: E = entry, S = stop (S > E), T = E − 2·(S − E)   # target = +2R downside
```

Walk bars `t0+1 … t0+W` (W = 30 daily bars). Per-bar rules:

- **WIN**: bar reaches target without also touching stop intrabar.
- **LOSS**: bar touches stop.
- **Same-bar ambiguity**: if a bar's range spans both target AND stop, we call it **LOSS**
  (conservative — assumes worst-case fill order). Documented, not tunable.
- **TIMEOUT**: neither hit within W bars. Record `r_multiple` from last-bar close.

`MAE` / `MFE` are max adverse / favorable excursion in R units within the walk.

## Feature freeze at T0
- All features computed on bars with index ≤ T0.
- Feature dict deep-copied and locked before the forward walk.
- A test asserts no forward-index access (`test_no_lookahead.py`).

## Preregistered thresholds — broad, interpretable
| Name | Definition |
|---|---|
| **Swing pivot** | Fractal pivot high/low with order=3, drawn from trailing 60 bars |
| **Untouched-level requirement** | No close touched the pivot for ≥ 20 bars prior |
| **BB/ATR compression** | BB width in bottom quartile of trailing 60 bars **OR** ATR(14) ÷ ATR(14, 60d mean) < 0.75 |
| **Fresh MACD (transition)** | Histogram sign change within last 3 bars **OR** MACD line cross within 3 |
| **Fresh MACD reacceleration** | Histogram same sign but abs(hist_t) > abs(hist_{t−1}) for last 2 bars |
| **EMA stack up** | EMA9 > EMA21 > EMA50 at bar |
| **EMA stack down** | EMA9 < EMA21 < EMA50 at bar |
| **Key level proximity** | Within 0.5 · ATR(14) of nearest pivot on the setup side |
| **Available space** | Distance from entry to next opposing pivot ≥ 2 · abs(entry − stop) |
| **Structural trigger** | Bar closes through the level (not just intrabar wick) |

## Regime split
Three buckets (BULL / BEAR / NEUTRAL) tagged on each bar using an SPY analysis that
mirrors `src/market_analyzer.MarketAnalyzer`'s composite score, re-implemented in
`research/regime.py` so nothing depends on the production import graph.

## Sample-size warning
- `n < 30` in any cell → ⚠ warning stamp on the row. Cell still rendered.
- Regime sub-cell with 0 samples renders as `N/A`, not omitted.

## Reporting
Per cell: `n`, `+2R %`, `mean_R`, `median_R`, `MAE`, `MFE`, `mean_bars_to_resolve`,
`{BULL, BEAR, NEUT} split`, `lift_vs_parent`, warning stamps.

Occurrence table (long-form): `symbol, t0, side, entry, stop, target, features (JSON),
outcome, r_multiple, bars_to_resolve, mae, mfe, regime, cell_names (JSON list)`.

Output tree per run:
```
research/results/<detector>_<yyyymmdd>_<hhmm>/
    stats.md          # human-readable cell table
    stats.csv         # same as CSV
    occurrences.csv   # every occurrence row
    manifest.json     # detector name, thresholds hash, run params, drop reasons
```

## Detectors — phase 1

**Fully specified now**:
1. `BREAKOUT_INSIDE_DAY_CONTINUATION`

**Stubs (specs identical, implementations TBD after phase-1 review)**:
2. `ASCENDING_COMPRESSION_BREAKOUT`
3. `DEMAND_PIVOT_REVERSAL`
4. `TREND_PULLBACK_CONTINUATION`
5. `OUTSIDE_DAY_LEVEL_REVERSAL`

## BREAKOUT_INSIDE_DAY_CONTINUATION — full definition

Setup family: a breakout of an untouched swing high, followed by an inside day
of consolidation, followed by continuation.

**Occurrence trigger** (at close of bar `t`, where the inside day is bar `t`):
- Bar `t` is an inside day: `high_t ≤ high_{t−1}` AND `low_t ≥ low_{t−1}`.

**Entry / stop / target**:
- Entry `E` = open of bar `t+1`.
- Stop `S` = min(low_t, low_{t−1}) − 0.1 · ATR(14). Below both the inside day and the prior bar.
- Target `T` = E + 2·(E − S). +2R.
- Side: **long only** for this detector.

**Cells reported**:
| # | Cell | Predicate on frozen features |
|---|---|---|
| 1 | `generic_inside_day` | (control — every inside day, no other filter) |
| 2 | `inside_day_uptrend` | (1) + EMA stack up at t |
| 3 | `inside_day_after_breakout` | (1) + bar t−1 was a real breakout of an untouched swing high |
| 4 | `inside_day_after_breakout_holding_above` | (3) + close_t > pre-breakout swing high |
| 5 | `#4 + compression` | (4) + BB/ATR compression at t |
| 6 | `#4 + fresh_MACD_reacceleration` | (4) + fresh MACD reacceleration at t |
| 7 | `#4 + compression + fresh_MACD_reacceleration` | (4) + (5's predicate) + (6's predicate) |

Parent for lift comparison:
- (2), (3) parent = (1)
- (4) parent = (3)
- (5), (6), (7) parent = (4)

## Non-goals in this phase
- No promotion to Top 10 / Telegram.
- No changes to production scoring, alerts, entries, ranking weights, or trade eligibility.
- No threshold tuning to hit an R target.
- No composite score.
- No wiring of `research/` into `src/`.

## Version
- v0.1 — 2026-09-15, initial preregistration.
