# PREREGISTRATION — Setup Context Research

**Locked before any backtest runs.** Any change to a definition below is a version bump
with a timestamp — no silent retuning.

**Version**: **v0.2** — 2026-09-15. Reflects reviewer directives on resolver outcomes,
level provenance, orthogonal cell design, gap handling, and Layer-2 semantic regime.
See `## Changelog` at the bottom for the diff from v0.1.

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

Given `(entry E, stop S, target T)` with `T = E ± 2·|E − S|` on the setup side,
walk bars `t0+1 … t0+W` (`W = 30` daily). Outcomes:

| Outcome | Definition |
|---|---|
| **WIN** | A bar reaches target AND does not also touch stop intrabar in the same bar. |
| **LOSS** | A bar touches stop AND does not also touch target intrabar in the same bar. |
| **AMBIGUOUS** | A single bar's range spans BOTH stop and target. First-touch order is **unknowable** from OHLC. |
| **TIMEOUT** | Neither stop nor target hit within W bars. `r_multiple` recorded from last bar's close. |

**Ambiguous is a first-class outcome.** Primary statistics do NOT coerce ambiguous
into any other bucket.

### Primary and sensitivity stats
For any cell subset:

- `n_total`, `n_win`, `n_loss`, `n_ambiguous`, `n_timeout`
- `n_scoreable = n_win + n_loss + n_timeout` (excludes AMBIGUOUS)
- **`primary_+2R_pct = n_win / n_scoreable`** (denominator excludes AMBIGUOUS)
- `ambiguous_rate = n_ambiguous / n_total`
- **`conservative_+2R_pct = n_win / n_total`** (ambiguous counted as non-win)
- **`optimistic_+2R_pct = (n_win + n_ambiguous) / n_total`** (ambiguous counted as win)
- Analogous `mean_R_primary` (excluding ambiguous), `mean_R_conservative` (ambig → −1), `mean_R_optimistic` (ambig → +2)

Sensitivity bounds define the honest range: `primary_+2R_pct` inside
`[conservative_+2R_pct, optimistic_+2R_pct]` always. Wide gap = high ambiguous
rate = tight-stop / high-volatility regime — report it, don't hide it.

### Same-bar-ambiguity gap-fill NOT counted here
Gap handling at ENTRY is separate — see `## Entry & gap handling` below.

### MAE / MFE
Recorded in R units across the walk regardless of outcome (including AMBIGUOUS).
MAE = max adverse excursion (positive number). MFE = max favorable.

## Production-resolver compatibility

The research resolver is not guaranteed identical to the bot's `+2R-before-−1R`
framework. When the bot repo is attached, `research/resolve.py` gains an
optional `bot_compat: bool` flag that mirrors the bot's semantics (including
any differences in ambiguous handling, gap policy, or TIMEOUT r_multiple).
When runs use `bot_compat=True`, results are stored in a separate output tree
under `research/results/<detector>_<ts>/bot_compat/` and rendered side by side
with the research-native results in `stats.md`. Divergences ≥ 2 pp between the
two sets are flagged with `⚑`.

Until the bot repo is attached, the research resolver is the only implementation;
this section is a forward-looking commitment, not code.

## Entry & gap handling

Preregistered: `entry = open of bar t0 + entry_bar_offset` (default `+1`, i.e.,
next-bar-open). Bar `t0 + entry_bar_offset` is the FIRST bar in the resolver
walk.

At the moment of that bar's open, we classify entry into one of four states:

| `entry_gap_flag` | Condition (long side; short is mirrored) | Handling |
|---|---|---|
| `clean` | `stop < open < target` | Normal resolution; walk starts at bar t0+off. |
| `gap_through_stop` | `open ≤ stop` | **Excluded from primary stats.** Reported as a diagnostic rate. Sensitivity: conservative counts as LOSS (r = −1); optimistic **also** counts as LOSS (no reasonable optimistic case; skipping the fill would reduce n which is more misleading). |
| `gap_through_target` | `open ≥ target` | **Excluded from primary stats.** Reported as a diagnostic rate. Sensitivity: conservative counts as timeout at open (r = (open − entry) / risk_unit — could be > +2R); optimistic counts as WIN (r = +2). |
| `above_but_reachable` | `entry < open < target` (long: `open > entry` since entry IS open; keeps flag reserved for short-side symmetry) | (Long: not applicable since entry := open. Short: analogous mirror.) |

The gap flags are stored per occurrence. Cells `gap=clean`, `gap=through_stop`,
`gap=through_target` render orthogonally.

## Feature freeze at T0
- All features computed on bars with index ≤ T0.
- Feature dict deep-copied and locked before the forward walk.
- Tested by `test_no_lookahead.py` (future-corruption test) and
  `test_bidc_detector.py::test_..._does_not_change_with_future_corruption`.

## Preregistered thresholds — broad, interpretable
| Name | Definition |
|---|---|
| **Swing pivot** | Fractal pivot high/low with order=3, drawn from trailing 60 bars |
| **Horizontal resistance / support** | ≥ 3 highs (resistances) or lows (supports) within ±0.25·ATR14 of each other, spanning ≥ 10 bars, all inside trailing 90 bars |
| **Known level** | Round number ($10.00 / $12.50 / $50.00 / $100.00 grid), prior-day-high, prior-day-low, prior-week-high, prior-week-low, prior-month-high, prior-month-low |
| **Untouched-level requirement** (swing pivots only) | No close touched the pivot for ≥ 20 bars prior. **Not** required for horizontal resistances or known levels. |
| **BB/ATR compression** | BB width in bottom quartile of trailing 60 bars **OR** ATR(14) ÷ mean(ATR(14), 60d) < 0.75 |
| **Fresh MACD (transition)** | Histogram sign change within last 3 bars **OR** MACD line cross within 3 |
| **Fresh MACD reacceleration** | Histogram same sign but abs(hist_t) > abs(hist_{t−1}) > abs(hist_{t−2}) |
| **EMA stack up** | EMA9 > EMA21 > EMA50 at bar |
| **EMA stack down** | EMA9 < EMA21 < EMA50 at bar |
| **Key level proximity** | Within 0.5 · ATR(14) of any level (any provenance) on the setup side |
| **Available space** | `room_to_next_level ≥ 2 · abs(entry − stop)` (measured in R units) |
| **Structural trigger** | Bar closes through the level (not just intrabar wick) |

## Level provenance

Every level referenced by an occurrence carries:
- `level_price` (float)
- `level_type` ∈ `{swing_pivot, horizontal_resistance, round_number, prior_day_high, prior_day_low, prior_week_high, prior_week_low, prior_month_high, prior_month_low}`
- `formed_at` (Timestamp — bar of formation for pivots; NA for round numbers)
- `provenance` (dict of type-specific metadata: `n_touches`, `tolerance_atr`, `first_touch_bars_ago`, etc.)

The BIDC detector accepts a breakout of **any** level type — not just an
untouched swing pivot. `level_type` is a cell axis, so lift can be measured
per provenance.

## Per-occurrence stored fields (in addition to entry/stop/target/features)

- `level_price` — the level that was broken (bull) or lost (bear)
- `level_type` — see above
- `level_formed_at` — timestamp (or NaT)
- `level_provenance` — JSON blob of type-specific metadata
- `breakout_age_bars` — bars since the breakout bar (0 = breakout on t−1, 1 = t−2, …)
- `distance_to_level_atr` — `(close_t − level_price) / ATR14` (signed; positive above)
- `room_to_next_level_atr` — distance from entry to next opposing level, ATR-normalized
- `room_to_next_level_R` — same distance in R units of THIS trade (`room_atr · ATR14 / risk_unit`)
- `entry_gap_flag` — one of `clean / gap_through_stop / gap_through_target / above_but_reachable`
- `regime_semantic` — Layer-2 tuple (see below)

## Regime split — Layer-2 semantic states (canonical)

Two axes, both from SPY only. **Full state stored per occurrence.** Optional
coarse buckets are report-time only.

### Trend axis (5-way)
| State | Condition (evaluated at SPY close of t0) |
|---|---|
| `STRONG_UPTREND` | EMA9 > EMA21 > EMA50 AND close > EMA20 AND ROC(30) > 5% |
| `UPTREND` | EMA20 > EMA50 AND close > EMA20 AND 2% < ROC(30) ≤ 5% |
| `SIDEWAYS` | Neither UPTREND nor DOWNTREND conditions met |
| `DOWNTREND` | EMA20 < EMA50 AND close < EMA20 AND −5% ≤ ROC(30) < −2% |
| `STRONG_DOWNTREND` | EMA9 < EMA21 < EMA50 AND close < EMA20 AND ROC(30) < −5% |

### Risk axis (3-way)
| State | Condition |
|---|---|
| `RISK_ON` | close in top 20% of trailing 60-day range AND ATR ratio (14 / 60d mean of 14) < 1.2 |
| `RISK_OFF` | close in bottom 20% of trailing 60-day range OR ATR ratio > 1.5 |
| `RISK_NEUTRAL` | Neither |

### Full state (canonical)
Tuple `(trend, risk)` — 15 possible values. Stored as `regime_semantic`
string like `UPTREND+RISK_ON`. Always the tag on each occurrence, always.

### Coarse buckets (report-only, optional)
Used ONLY when a Layer-2 cell has n < 30. Not stored on occurrences.
| Bucket | Members |
|---|---|
| `BULL_ENV` | `STRONG_UPTREND+*`, `UPTREND+RISK_ON`, `UPTREND+RISK_NEUTRAL` |
| `BEAR_ENV` | `STRONG_DOWNTREND+*`, `DOWNTREND+RISK_OFF`, `DOWNTREND+RISK_NEUTRAL` |
| `CHOP` | `SIDEWAYS+*`, remaining crosses (`UPTREND+RISK_OFF`, `DOWNTREND+RISK_ON`) |

The bot's Layer-2 taxonomy is preserved verbatim once the bot repo is attached;
the definitions above are a placeholder that produces the SAME string format
as observed in Telegram alerts. Divergence, if any, will bump the version.

## Sample-size warning
- `n_scoreable < 30` in any cell → ⚠ warning. Cell still renders.
- Regime sub-cell with 0 samples renders as `N/A`, not omitted.

## Reporting

Per cell, all columns:
- `n_total`, `n_win`, `n_loss`, `n_ambiguous`, `n_timeout`, `n_scoreable`
- `primary_+2R_pct`, `conservative_+2R_pct`, `optimistic_+2R_pct`
- `ambiguous_rate`, `gap_through_stop_rate`, `gap_through_target_rate`
- `mean_R_primary`, `mean_R_conservative`, `mean_R_optimistic`, `median_R_primary`
- `mean_MAE_R`, `mean_MFE_R`, `mean_bars_to_resolve`
- Layer-2 semantic split: one column per non-zero state in this run
- `lift_vs_parent_pct` (delta on `primary_+2R_pct` vs named parent)
- `warn_low_n` (⚠ if `n_scoreable < 30`)

Occurrence table columns: all fields listed in `## Per-occurrence stored fields`
plus the frozen feature dict fields (JSON-encoded).

Output tree per run:
```
research/results/<detector>_<yyyymmdd>_<hhmm>/
    stats.md          # human-readable cell table
    stats.csv         # same as CSV
    occurrences.csv   # every occurrence row
    manifest.json     # detector name, thresholds hash, run params, drop reasons
    # (when bot_compat=True on a subsequent run)
    bot_compat/
        stats.md
        stats.csv
        occurrences.csv
```

## Detectors — phase 1

**Fully specified now**:
1. `BREAKOUT_INSIDE_DAY_CONTINUATION`

**Stubs (specs TBD after v0.2 review)**:
2. `ASCENDING_COMPRESSION_BREAKOUT`
3. `DEMAND_PIVOT_REVERSAL`
4. `TREND_PULLBACK_CONTINUATION`
5. `OUTSIDE_DAY_LEVEL_REVERSAL`

## BREAKOUT_INSIDE_DAY_CONTINUATION — full definition

Setup family: a breakout of a level (any provenance), followed by an inside day
of consolidation, followed by continuation.

**Occurrence trigger** (at close of bar `t`, where the inside day is bar `t`):
- Bar `t` is an inside day: `high_t ≤ high_{t−1}` AND `low_t ≥ low_{t−1}`.

**Level context** — evaluated at bar t (looks back only):
- Enumerate all levels in the trailing 90 bars from all three provenance types
  (swing_pivot, horizontal_resistance, known_level).
- Find the most recent bar `b ≤ t − 1` at which `close_b > level_price AND
  close_{b−1} ≤ level_price` (a real close-through breakout, not just a wick).
- If found: record `broken_level` (price, type, formed_at, provenance),
  `breakout_age_bars = (t − 1) − b_iloc`, `holding_above_at_t = close_t > broken_level`.
- If none in window: `was_breakout = False`, other fields NaN.

**Entry / stop / target**:
- Entry `E` = open of bar `t+1`.
- Stop `S` = min(low_t, low_{t−1}) − 0.1 · ATR(14) at bar t. Below inside day AND prior bar.
- Target `T` = E + 2·(E − S). +2R.
- Side: **long only** for this detector.

**Entry gap classification** at open of bar `t+1`: see `## Entry & gap handling`.

### Cells reported — orthogonal PLUS cascade

Cells are organized in three groups. Each is rendered independently. **A modifier's
lift is meaningful in the orthogonal group; the cascade is retained because you
explicitly asked to test it.**

#### Group A — BASE (control)
| # | Cell | Predicate |
|---|---|---|
| A1 | `generic_inside_day` | (all inside days — the parent for all orthogonal modifiers) |

#### Group B — Orthogonal single modifiers (each parent = `generic_inside_day`)
| # | Cell | Predicate |
|---|---|---|
| B1 | `+ema_stack_up` | inside_day AND ema_stack_up |
| B2 | `+after_breakout_any_level` | inside_day AND was_breakout_at_tm1 |
| B3 | `+holding_above` | inside_day AND was_breakout_at_tm1 AND holding_above |
| B4 | `+compression` | inside_day AND compression |
| B5 | `+fresh_macd_reaccel_up` | inside_day AND fresh_macd_reaccel_up |
| B6 | `+room_to_next_level_ge_2R` | inside_day AND room_to_next_level_R ≥ 2 |
| B7 | `+level_type=swing_pivot` | inside_day AND was_breakout AND level_type == swing_pivot |
| B8 | `+level_type=horizontal_resistance` | inside_day AND was_breakout AND level_type == horizontal_resistance |
| B9 | `+level_type=known_level` | inside_day AND was_breakout AND level_type ∈ round_number/prior_day_high/… |
| B10 | `+breakout_age=0` | inside_day AND breakout_age_bars == 0 |
| B11 | `+breakout_age=1_to_2` | inside_day AND 1 ≤ breakout_age_bars ≤ 2 |
| B12 | `+breakout_age=3plus` | inside_day AND breakout_age_bars ≥ 3 |
| B13 | `+gap=clean` | inside_day AND entry_gap_flag == clean |

#### Group C — Cascade (nested, retained per your original spec)
| # | Cell | Predicate | Parent |
|---|---|---|---|
| C1 | `cascade_after_breakout` | inside_day AND was_breakout_at_tm1 | A1 |
| C2 | `cascade_holding_above` | C1 AND holding_above | C1 |
| C3 | `cascade_holding_plus_compression` | C2 AND compression | C2 |
| C4 | `cascade_holding_plus_fresh_macd` | C2 AND fresh_macd_reaccel_up | C2 |
| C5 | `cascade_holding_plus_both` | C2 AND compression AND fresh_macd_reaccel_up | C2 |

## Non-goals in this phase
- No promotion to Top 10 / Telegram.
- No changes to production scoring, alerts, entries, ranking weights, or trade eligibility.
- No threshold tuning to hit an R target.
- No composite score.
- No wiring of `research/` into `src/`.
- No implementation of detectors 2–5 (spec-only in this preregistration).

## Changelog

### v0.2 — 2026-09-15 — reviewer directives (before running phase 1)
- **Resolver**: four outcomes now `WIN / LOSS / AMBIGUOUS / TIMEOUT`. Ambiguous no longer coerced to LOSS. Primary stats use `n_scoreable = wins + losses + timeouts` as denominator. `conservative_+2R_pct` (ambig → non-win) and `optimistic_+2R_pct` (ambig → win) reported as sensitivity bounds.
- **Bot compat**: preregistered a hook for a future `bot_compat=True` mode that mirrors the bot repo's `+2R-before-−1R` semantics. When both run, `bot_compat/` results sit alongside the research-native set with divergence flags ≥ 2 pp.
- **BIDC cells**: split into **Group A base**, **Group B orthogonal** (13 single-modifier cells all parented to A1), and **Group C cascade** (the original nested chain, retained). Compression, MACD reaccel, EMA stack, room, level type, breakout age, and gap state are each testable orthogonally.
- **Level provenance**: no longer requires an untouched ≥20-bar swing pivot. Any of `{swing_pivot, horizontal_resistance, round_number, prior_day_high/low, prior_week_high/low, prior_month_high/low}` qualifies. `level_type` is stored per occurrence and is a cell axis.
- **Per-occurrence fields added**: `breakout_age_bars`, `distance_to_level_atr`, `room_to_next_level_atr`, `room_to_next_level_R`, level provenance dict.
- **Layer-2 semantic regime**: canonical 5×3 trend×risk cross (15 states). Full state stored on every occurrence. Coarse `BULL_ENV / BEAR_ENV / CHOP` buckets remain reporting-only, applied when a Layer-2 cell has n_scoreable < 30.
- **Entry & gap handling**: preregistered flags `clean / gap_through_stop / gap_through_target / above_but_reachable`. Gap-through-stop / gap-through-target rows are **excluded from primary stats** and reported as diagnostic rates; sensitivity bounds are defined explicitly.

### v0.1 — 2026-09-15 — initial preregistration
See git history for full v0.1 content.
