# PREREGISTRATION — Setup Context Research

**Locked before any backtest runs.** Any change to a definition below is a version bump
with a timestamp — no silent retuning.

**Version**: **v0.3** — 2026-09-16. Context Layer / Research Integrity Expansion.
Adds preregistered semantics for supply/demand zones, relative-strength vs SPY,
SMA trend structure, MACD momentum, TTM squeeze, extended Bollinger, a
volatility/compression label, orthogonal + interaction cells for context,
statistical reporting (bootstrap CIs), stability surfaces, prefix-replay and
append-future invariance tests, timeframe discipline, and a research ledger.
See `## Changelog` at the bottom for v0.2 → v0.3 diff. v0.1/v0.2 kept.

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

## Context Layers (v0.3) — one preregistration section per layer

### Guiding principles for v0.3
- **No composite score.** Weighted sums of layers, "+1 per condition" counters,
  or any single-number "confluence" number are non-goals in perpetuity for
  this research module.
- **Each layer is a separate observable dimension** stored as its own
  namespaced feature block in the occurrence record.
- **Every layer must be causal** — future bars must NEVER alter historical
  signal-time features. Enforced by `test_prefix_replay.py` and per-layer
  append-future invariance tests.
- **Thresholds and windows are preregistered here.** Implementation must
  match. Tuning against results = version bump with justification.
- **Daily-first.** Every layer below is preregistered on daily bars. An
  intraday variant is added ONLY if the intraday cache is complete, aligned
  to the daily universe, and demonstrably causal by prefix-replay. Absent
  that, intraday fields are stored as `UNAVAILABLE` with `_source_timeframe`
  set to `"1d"` — never silently backfilled from daily.
- **Historical regime reconstruction.** The regime tag on every occurrence
  is the regime that was OBSERVABLE at the occurrence's timestamp using only
  SPY bars ≤ t. Never attach today's SPY snapshot to a historical setup.
- **Missing ≠ neutral.** Every field below has one of two missing-value
  policies, chosen at preregistration time and never mixed:
  - `UNAVAILABLE` — the input data was absent, insufficient, or below the
    preregistered minimum observation count. The field is a string
    `"UNAVAILABLE"` (for label fields) or `None` (for numeric fields), and
    the accompanying `_availability` flag is `False`.
  - `UNKNOWN` — the input was present but the classifier's own rules did
    not resolve to a state. Stored as the literal `"UNKNOWN"` string.

  Neither `UNAVAILABLE` nor `UNKNOWN` may be coerced to `NEUTRAL`, `FLAT`,
  `False`, `0`, `no-signal`, or any other "silent-default" value. Cells
  keyed off missing fields must render with `n_UNAVAILABLE` and `n_UNKNOWN`
  columns rather than absorb them into a base bucket.

### Mathematical definitions of subjective terms (v0.3 addendum)

Every term that could be read as subjective is pinned to a numeric
predicate. Implementation must match these definitions exactly.

**Supply / demand terms**

| Term | Definition |
|---|---|
| **Base** | 2, 3, or 4 consecutive bars each with `high − low ≤ 0.7 · ATR14` measured at the impulse bar. Bases are searched immediately before the impulse bar; the LONGEST-first search (4 → 3 → 2) wins so that any longer valid base is preferred. |
| **Departure (up)** | Bar `i` where `close_i − open_i ≥ 1.5 · ATR14_i` AND `close_i > high_{i−1}`. Both conditions required — magnitude alone is not a departure. |
| **Departure (down)** | Bar `i` where `open_i − close_i ≥ 1.5 · ATR14_i` AND `close_i < low_{i−1}`. |
| **Pivot** | A fractal pivot (order 3): bar `i` such that `high_i = max(high_{i−3..i+3})` (pivot high) or `low_i = min(low_{i−3..i+3})` (pivot low). The pivot ANCHORS at i and is only KNOWN at i+3 (needs 3 future bars). |
| **Repeated rejection** | ≥ 3 highs within `0.25 · ATR14` of each other, spanning ≥ 10 bars, all inside the trailing 90 bars. Symmetric for lows. Same definition as **horizontal resistance / support**. |
| **Zone width** | `(price_high − price_low) / ATR14_at_known_at`. Reported as `width_atr`. No implicit cap; a wide zone is a wide zone. |
| **Zone creation** | The **base-start bar** timestamp (`created_at`). A zone is CREATED at the base's first bar but not yet OBSERVABLE — it can only be labeled after the impulse. |
| **Zone confirmation / known_at** | The **impulse bar** timestamp (`known_at_bar`). The zone becomes an observable feature at the close of this bar. Every context computation is gated by `known_at_bar ≤ t`. |
| **Touch (post-known_at)** | Any bar `j > known_at_bar` where `low_j ≤ price_high AND high_j ≥ price_low` (the bar's range intersects the zone). Counted for `touches_since_creation`. |
| **Freshness** | `max(0.0, 1.0 − 0.2 · touches_since_creation)`. Floors at 0 after 5 touches. A zone is "fresh" iff `freshness = 1.0` (untouched since known_at). |
| **Invalidation (demand)** | The first bar `j > known_at_bar` where `close_j < price_low − 0.1 · ATR14_at_known_at`. From that bar forward, `active = False` and `invalidated_at = index[j]`. |
| **Invalidation (supply)** | Symmetric: the first bar `j > known_at_bar` where `close_j > price_high + 0.1 · ATR14_at_known_at`. |
| **Room to opposing structure** | For a long, `room_to_supply_atr = (nearest_active_supply.price_low − close_t) / ATR14_t`. `room_to_supply_R = (nearest_active_supply.price_low − close_t) / planned_risk_unit_t`. NaN if no active supply above `close_t`. Symmetric for shorts. |

**Trend / momentum terms**

| Term | Definition |
|---|---|
| **SMA slope class** | On normalized slope `s = sma_t / sma_{t−L} − 1` with preregistered `L` per period (§ 4). `RISING` iff `s ≥ +0.01`; `FALLING` iff `s ≤ −0.01`; `FLAT` otherwise. `UNAVAILABLE` iff fewer than `L + period` bars of history. |
| **SMA reclaim at t** | `close_{t−1} ≤ sma_{t−1}` AND `close_t > sma_t`. Deterministic single-bar event. |
| **SMA loss at t** | Mirror: `close_{t−1} ≥ sma_{t−1}` AND `close_t < sma_t`. |
| **"Near" a level / SMA** | `|distance| ≤ 0.5 · ATR14_t` on the same timeframe. Applied identically to swing pivots, horizontal levels, zones, and SMAs. |
| **MACD "fresh" transition** | Histogram sign change within the last 3 bars OR MACD-line signal cross within 3 bars (using 12/26/9 EMA). |
| **MACD state neutral band** | `|macd_hist| < 0.05 · ATR14`. Inside the band → `NEUTRAL`. Outside → BULLISH / BEARISH per hist sign, and expanding vs fading per hist slope sign. |
| **TTM squeeze on** | `BB_upper < KC_upper` AND `BB_lower > KC_lower`, where BB = SMA(close, 20) ± 2·stddev(close, 20) and KC = EMA(close, 20) ± 1.5·ATR(20). |
| **BB compression** | `bb_width_percentile ≤ 0.20` (bottom quintile of trailing 60 bars). |
| **BB expansion** | `bb_width_percentile ≥ 0.80`. |
| **Compression (composite label input)** | `bb_width_percentile ≤ 0.20` OR `atr_ratio_60 < 0.85` OR `squeeze_on`. |

None of the terms above admit a "loose" or "roughly" reading. When the
implementation cannot compute a term due to missing inputs, the term
resolves to `UNAVAILABLE` per **Missing ≠ neutral** above, never to a
default-neutral.

### Minimum observation rules (v0.3)

A feature is `UNAVAILABLE` unless its minimum input count is met. Below
those minimums, the field IS NOT SILENTLY OMITTED — it is stored with its
namespace-prefixed key set to `None` (numeric) or `"UNAVAILABLE"` (label),
and a matching `_availability` sub-key set to `False`.

| Feature block | Minimum |
|---|---|
| `supply_demand.*` zones | ≥ `atr_period + impulse_base_max + 1` = ≥ 19 daily bars. |
| `supply_demand.*` context | ≥ 1 active zone of the queried type OR field is `None` (never coerced to 0-distance). |
| `relative_strength.rs_spy_1d/5d/10d/20d` | ≥ `N + 1` aligned SPY+stock bars. |
| `relative_strength.rs_class` | Requires `rs_spy_20d` present. Below the min → `"UNAVAILABLE"`. |
| `relative_strength.rs_during_spy_weakness_*` | ≥ **10** qualifying SPY weakness bars in the trailing 60-bar window. |
| `relative_strength.rs_during_spy_strength_*` | ≥ **10** qualifying SPY strength bars in the trailing 60-bar window. |
| `relative_strength.stock_hh_spy_no_hh` / … | ≥ `structure_lookback + 2` = ≥ 22 aligned bars. |
| `market.spy_regime_semantic` | ≥ 60 SPY bars for risk axis; ≥ 55 for trend axis. Either axis short → components `UNKNOWN` and semantic label carries the `UNKNOWN` on the missing axis. |
| `trend.stock_sma_N` | ≥ `N` bars for SMA level; ≥ `N + lookback_N` bars for its slope classification (`lookback_N` per § 4). |
| `momentum.macd_*` | ≥ 26 + 9 + 3 = 38 bars for full MACD + 3-bar slope; below → `UNAVAILABLE`. |
| `compression_volatility.ttm_*` | ≥ 40 bars (20 for BB/KC + 20 for the linear-regression momentum window). |
| `compression_volatility.bb_*` | ≥ 60 bars (20-period BB + 60-bar percentile window). |
| `compression_volatility.volatility_label` | Requires ALL of `bb_width_percentile`, `atr_ratio_60`, `squeeze_on` available; else `"UNAVAILABLE"`. |

Cells built on these features report `n_UNAVAILABLE` alongside their
`n_TRUE / n_FALSE / n_UNKNOWN` counts. Cells never marginalize
`UNAVAILABLE` away.

### Correlated feature families (v0.3)

Certain features are **statistically correlated by construction**. They
are stored as separate observables (each is a raw signal), but downstream
research MUST NOT count them as independent confirmations. Interaction
cells that combine members of the same family are flagged
`redundant_by_construction` in the cell registry and are excluded from
the "orthogonal modifiers" group.

| Family | Members | Reason for correlation |
|---|---|---|
| **MACD family** | `macd.macd_line`, `macd.macd_signal`, `macd.macd_hist`, `macd.*_slope`, `macd.macd_state` | All derived from the same 12/26/9 EMAs of one close series. |
| **SMA stack family** | `sma20_gt_sma50`, `sma50_gt_sma100`, `sma100_gt_sma200`, `bullish_full_stack`, `sma_stack_state` | Each stack boolean is the pairwise ordering that also determines the "full stack". |
| **SMA-vs-price family** | `above_sma_N`, `distance_to_sma_N_pct`, `distance_to_sma_N_atr`, `nearest_sma_period` | All read the same `(close, sma_N)` pair. |
| **SMA slope family** | `sma_N_slope`, `sma_N_slope_class`, `sma_N_slope_lookback` | The class is a threshold on the raw slope. |
| **Volatility-compression family** | `bb_width`, `bb_width_percentile`, `atr_ratio_60`, `squeeze_on`, `volatility_label`, `bb_state == COMPRESSION` | BB width, ATR compression, and TTM squeeze all measure the same underlying volatility contraction; the semantic label is derived from them. |
| **BB-midline / SMA20 overlap** | `bb_middle`, `sma_20`, `price_above_midline`, `above_sma20` | `bb_middle == sma(close, 20)` by definition. |
| **RS trajectory family** | `rs_spy_Nd` for various N, `rs_slope_short`, `rs_slope_medium`, `rs_acceleration`, `rs_class` | Slopes are finite differences of the same lookback returns; class is a threshold on `rs_spy_20d`. |
| **Zone-derived room family** | `room_to_supply_atr`, `room_to_supply_R`, `nearest_supply_distance_atr` | All read the same nearest-active-supply object. |

The report renders raw fields and their derived class/state fields side
by side but never sums them.

### 1. Supply / Demand zones (`research/supply_demand.py`)
Deterministic, auditable, no future-bar leakage.

**Zone construction — v0.3 first pass ("base + impulse" rule)**:
- A **demand zone** is emitted at the close of bar `i` iff:
  - Bars `[i−N .. i−1]` form a **base**: `N ∈ {2, 3, 4}` consecutive bars
    whose range each is ≤ `0.7 · ATR14`.
  - Bar `i` is an **impulse up**: `close_i − open_i ≥ 1.5 · ATR14` AND
    `close_i > high_{i−1}`.
- A **supply zone** is emitted symmetrically for impulsive down bars.
- Zone `price_low` / `price_high` = min-low / max-high of the base bars.
- Fields stored per zone:
  ```
  zone_id                    (deterministic hash of symbol + created_at + zone_type)
  zone_type                  ("demand" | "supply")
  price_low, price_high, midpoint
  source_bar                 (impulse bar timestamp — where the zone is "created" from)
  known_at_bar               (impulse bar timestamp — first bar at which the zone is observable)
  created_at                 (base-start bar timestamp, for reference)
  source_reason              ("base_impulse")
  age_bars                   (bars since known_at as of query time)
  touches_since_creation     (bars where price re-entered the zone range after known_at)
  freshness                  (1.0 − 0.2 · touches_since_creation, floored at 0)
  departure_atr              (impulse-bar range ÷ ATR14)
  departure_pct              (impulse-bar close-to-open ÷ open)
  width_atr                  ((price_high − price_low) ÷ ATR14 at known_at)
  active                     (True until invalidated)
  invalidated_at             (bar at which a close beyond the far side breaks the zone)
  ```
- **Invalidation**:
  - Demand invalidated on any bar with `close < price_low − 0.1·ATR14_at_known_at`
  - Supply invalidated on any bar with `close > price_high + 0.1·ATR14_at_known_at`

Per-occurrence context (computed at signal-time T only, no future bars):
```
nearest_demand_distance_atr
nearest_supply_distance_atr
inside_demand_zone           (bool)
inside_supply_zone           (bool)
demand_zone_freshness        (of the nearest active demand zone; NaN if none)
supply_zone_freshness        (of the nearest active supply zone; NaN if none)
demand_zone_age_bars
supply_zone_age_bars
room_to_supply_atr           (long-side ceiling; NaN if no active supply above price)
room_to_demand_atr           (short-side floor; NaN if no active demand below price)
room_to_supply_R             (= room_to_supply_atr · ATR14 ÷ planned_risk_unit)
room_to_demand_R             (= room_to_demand_atr · ATR14 ÷ planned_risk_unit)
```
The R denominator is the frozen signal-time planned_risk_unit — **never** a
future-adjusted one.

### 2. Relative strength vs SPY (`research/relative_strength.py`)
Multi-lookback returns + slopes + acceleration + a preregistered class. Full
signal-time SPY alignment; no forward-fill through gaps.

**Return lookbacks** (daily phase 1; intraday timeframes stored as NaN with
`unavailable=True` flag until intraday data lands):
```
rs_spy_1d, rs_spy_5d, rs_spy_10d, rs_spy_20d
```
Where `rs_spy_Nd = stock_return_Nd − spy_return_Nd` and both returns use
CLOSE-to-CLOSE only on bars where both series have observations.

**Slopes / acceleration** (deterministic finite diffs, normalized):
```
rs_slope_short   = (rs_spy_5d − rs_spy_1d) / 4
rs_slope_medium  = (rs_spy_20d − rs_spy_5d) / 15
rs_acceleration  = rs_slope_short − rs_slope_medium
```

**Class** (preregistered thresholds on `rs_spy_20d`):
```
OUTPERFORMING     rs_spy_20d ≥  +5.0%
NEUTRAL           −2.0% < rs_spy_20d < +5.0%
UNDERPERFORMING   rs_spy_20d ≤ −2.0%
```

**RS during SPY weakness / strength** (trailing 60 bars):
- SPY weakness bars = bars where `spy_close_t < spy_close_{t−1}` in the window.
- SPY strength bars = bars where `spy_close_t > spy_close_{t−1}`.
- Fields:
  ```
  rs_during_spy_weakness_stock_cum      (stock cum-return on weakness bars)
  rs_during_spy_weakness_spy_cum        (SPY cum-return on same bars)
  rs_during_spy_weakness_diff           (stock − SPY on weakness bars)
  rs_during_spy_weakness_frac_outperformed
  rs_during_spy_weakness_frac_stock_positive
  rs_during_spy_weakness_stock_max_dd

  rs_during_spy_strength_stock_cum
  rs_during_spy_strength_spy_cum
  rs_during_spy_strength_diff
  rs_during_spy_strength_frac_underperformed
  rs_during_spy_strength_frac_stock_negative
  rs_during_spy_strength_stock_max_ru
  ```

**Structural divergence booleans** (trailing 20 bars for structure):
```
stock_hh_spy_no_hh           stock made a HH; SPY did not (compare to trailing 20-day max)
stock_hl_spy_ll              stock made a HL; SPY made a LL
stock_holds_low_spy_breaks   stock stayed above its 20-day low; SPY closed through its 20-day low
stock_breaks_high_spy_does_not
```
**VWAP-based divergence**: omitted in phase 1 (no intraday data source yet).
Documented here as an intentional gap.

### 3. SPY regime (reuse of Layer-2 semantic regime, expose components)
`spy_regime_semantic` (canonical string label like `UPTREND+RISK_ON`) and
`spy_regime_coarse` remain as in v0.2. v0.3 exposes the causal COMPONENTS
that produced the semantic state:
```
spy_trend_component          (STRONG_UPTREND | UPTREND | SIDEWAYS | DOWNTREND | STRONG_DOWNTREND | UNKNOWN)
spy_risk_component           (RISK_ON | RISK_NEUTRAL | RISK_OFF | UNKNOWN)
spy_regime_conflict          (True iff coarse bucket is CHOP — trend and risk disagree)
spy_regime_confidence        ("high" | "medium" | "low") derived deterministically from:
    - "high"   if trend ∈ {STRONG_UPTREND, STRONG_DOWNTREND} AND risk aligns
    - "medium" if trend and risk not conflicting but neither is STRONG
    - "low"    if regime_conflict OR either component is UNKNOWN
```
Coarse remains **reporting-only**. Full label + components are always stored.

### 4. SMA trend structure (`research/sma_trend.py`)
Simple moving averages as separate observable dimensions. **No SMA score.**

**SMA set**: 20, 50, 100, 200 — computed at bar t using `close.iloc[:t+1]`.
If insufficient history for a given period, that SMA row is stored as
`unavailable=True` with all its derived fields as NaN — **never**
silently shortened.

**Per-occurrence fields** (with `_stock_` prefix; SPY analogs get `_spy_`):
```
sma_20, sma_50, sma_100, sma_200
distance_to_sma20_pct       ((close − sma) ÷ sma)
distance_to_sma50_pct
distance_to_sma100_pct
distance_to_sma200_pct
distance_to_sma20_atr       ((close − sma) ÷ ATR14)
distance_to_sma50_atr
distance_to_sma100_atr
distance_to_sma200_atr
above_sma20                  (close > sma)
above_sma50
above_sma100
above_sma200
```

**Slope calculation** (normalized, deterministic):
- Lookback per SMA (preregistered): `SMA20 → 10 bars; SMA50 → 20 bars; SMA100 → 40 bars; SMA200 → 80 bars`.
- `sma_slope = (sma_now / sma_lookback_bars_ago) − 1.0`. Fraction, not %.
- **Classification** (preregistered):
  ```
  RISING   sma_slope ≥  +0.01
  FLAT    −0.01 < sma_slope < +0.01
  FALLING sma_slope ≤ −0.01
  ```
  Same threshold across all four SMAs (interpretable, no tuning).

**Stack booleans**:
```
sma20_gt_sma50
sma50_gt_sma100
sma100_gt_sma200
bullish_full_stack        (all three True)
bearish_full_stack        (all three False AND their opposites all True)
sma_stack_state           ("BULLISH_STACK" | "BEARISH_STACK" | "MIXED")
```

**Reclaim / loss events** (causal, deterministic):
- **Reclaim SMA_N at bar t**: `close_{t−1} ≤ sma_{t−1}` AND `close_t > sma_t`.
- **Loss SMA_N at bar t**: `close_{t−1} ≥ sma_{t−1}` AND `close_t < sma_t`.
- `bars_since_reclaim_smaN` and `bars_since_loss_smaN` — number of bars
  since the most recent event of that type in trailing 250 bars; NaN if no
  event in window.
- `holding_above_sma_after_reclaim`: bool — bars since reclaim > 0 AND every
  intervening close ≥ SMA at close.
- `holding_below_sma_after_loss`: symmetric.

**Nearest-SMA proximity** (dynamic-structure surface):
```
nearest_sma_value            (of {sma20, sma50, sma100, sma200}, choosing the one with min |close − sma|)
nearest_sma_period           (20 | 50 | 100 | 200)
nearest_sma_distance_atr     (signed: positive if price above)
nearest_sma_distance_pct
entry_near_sma20             (|distance_to_sma20_atr| ≤ 0.5)
entry_near_sma50
entry_near_sma100
entry_near_sma200
```
`entry_near_X` uses ≤ 0.5·ATR14 as the preregistered "near" threshold, same
across periods.

**Stock-vs-SPY SMA context** (all `spy_*` fields computed on the same rules):
Derived explicit booleans:
```
stock_above_sma50_spy_below_sma50
stock_above_sma200_spy_below_sma200
stock_sma50_rising_spy_sma50_falling
stock_bullish_stack_spy_not_bullish_stack
```
No aggregation; each remains a standalone dimension.

**Multi-timeframe SMAs** (phase 2 — intraday not yet in the pipeline):
Documented as an intentional gap. When 1h / 4h daily-close feeds land, HTF
SMAs will follow the **last-completed-bar** rule: the value at signal time T
must come from the last HTF bar whose close_timestamp ≤ T. Any HTF SMA
computed from a currently-open (unfinished) bar is a **causality violation**
and blocks the run.

### 5. MACD momentum (`research/momentum.py`)
Raw semantics, no bullish/bearish black-box flag.
Preregistered: **12/26/9 EMA MACD**.

Per-occurrence fields:
```
macd_line, macd_signal, macd_hist
macd_line_slope           (line_t − line_{t−3}) / 3
macd_signal_slope         (signal_t − signal_{t−3}) / 3
macd_hist_slope           (hist_t − hist_{t−3}) / 3
macd_hist_acceleration    (hist_slope_t − hist_slope_{t−3}) / 3
macd_above_zero           (macd_line > 0)
macd_below_zero           (macd_line < 0)
macd_above_signal         (macd_line > macd_signal)
bars_since_macd_cross     (bars since last `sign(macd_hist)` flip; NaN if none in trailing 250)
cross_direction           ("up" | "down" | "none")
macd_state                ("BULLISH_EXPANDING" | "BULLISH_FADING" | "BEARISH_EXPANDING" | "BEARISH_FADING" | "NEUTRAL")
```

**State thresholds** (preregistered):
- `NEUTRAL` if `abs(macd_hist) < 0.05 · atr14`.
- `BULLISH_EXPANDING` if `hist > 0 AND hist_slope > 0`.
- `BULLISH_FADING`    if `hist > 0 AND hist_slope ≤ 0`.
- `BEARISH_EXPANDING` if `hist < 0 AND hist_slope < 0`.
- `BEARISH_FADING`    if `hist < 0 AND hist_slope ≥ 0`.

### 6. TTM Squeeze (`research/squeeze.py`)
Exact math (John Carter's original formulation, adapted deterministic):
- Bollinger Bands: `SMA(close, 20) ± 2·stddev(close, 20)`.
- Keltner Channels: `EMA(close, 20) ± 1.5 · ATR(20)` (**ATR period 20** here,
  not the 14 used elsewhere; preregistered).
- `squeeze_on` at bar t iff `BB_upper_t < KC_upper_t AND BB_lower_t > KC_lower_t`.
- `squeeze_off` = NOT `squeeze_on`.
- **TTM momentum value** = linear-regression fit at bar t of the series
  `close − ((donchian_high_20 + donchian_low_20) / 2 + SMA(close, 20)) / 2`,
  taken over the last 20 bars. Documented as exactly that formula, not a
  library alias.

Per-occurrence fields:
```
squeeze_on                 (bool)
squeeze_off                (bool)
squeeze_duration_bars      (contiguous bars where squeeze_on preceding t, 0 if squeeze_off at t)
bars_since_squeeze_release (bars since last off→on-to-off transition; NaN if none in 250)
first_release_bar          (timestamp of that release)
squeeze_release_direction  ("up" | "down" | "none") — sign of ttm_momentum_value at first_release_bar
ttm_momentum_value
ttm_momentum_slope         (momentum_t − momentum_{t−3}) / 3
ttm_momentum_acceleration  (slope_t − slope_{t−3}) / 3
ttm_momentum_positive      (bool)
ttm_momentum_negative      (bool)
```
**Correlation note (preregistered)**: TTM squeeze status is highly
correlated with Bollinger compression. They are stored as independent
observables here; downstream research must NOT treat them as independent
confirmations. Interaction cells that require both must be labeled
explicitly as `redundant_by_construction` in cell definitions.

### 7. Bollinger extended (`research/volatility.py`)
Per-occurrence fields:
```
bb_upper, bb_middle, bb_lower
bb_width
bb_width_percentile       (in trailing 60 bars, from math_utils.bb_width_percentile)
bb_percent_b              ((close − lower) / (upper − lower), 0..1)
bb_midline_slope          (mid_t − mid_{t−3}) / 3, normalized by mid_{t-3}
bb_width_slope            (width_t − width_{t−3}) / 3, normalized by width_{t-3}
bb_expanding              (bb_width_slope > +0.05 — preregistered)
bb_contracting            (bb_width_slope < −0.05)
price_above_midline
price_below_midline
touching_upper_band       (close ≥ 0.98 · bb_upper)
touching_lower_band       (close ≤ 1.02 · bb_lower)
bb_state                  ("COMPRESSION" | "EXPANSION" | "NORMAL")
```

**BB state** (preregistered):
- `COMPRESSION` if `bb_width_percentile ≤ 20%`.
- `EXPANSION`   if `bb_width_percentile ≥ 80%`.
- `NORMAL`      else.

### 8. Volatility / compression semantic label
Derived from BB percentile, ATR percentile, and TTM squeeze status. Raw
inputs remain first-class. Label is one of:
```
DEEP_COMPRESSION    bb_width_pct ≤ 10  AND  atr_ratio_60 < 0.75  AND  squeeze_on
COMPRESSION         bb_width_pct ≤ 20  OR   atr_ratio_60 < 0.85  OR   squeeze_on
NORMAL              (default)
EXPANDING           bb_expanding AND bb_width_pct ≥ 60
HIGH_VOLATILITY     atr_ratio_60 ≥ 1.5
```
Precedence when multiple match: `DEEP_COMPRESSION > HIGH_VOLATILITY >
EXPANDING > COMPRESSION > NORMAL`.
The label is a DESCRIPTION, not a score. Raw components always available.

### 9. Feature-layer architecture — per-occurrence record structure
Namespaces (dot-separated keys inside `Occurrence.features`):
```
identity.*        (ticker, timestamp, direction, detector, detector_version)
setup.*           (setup-specific existing features)
structure.*       (breakout level + supply/demand + room fields + level_type)
relative_strength.*  (rs_spy_*, rs_slope_*, rs_class, rs_during_*, structural divergence)
market.*          (spy_regime_semantic, spy_regime_coarse, spy_trend_component, spy_risk_component, spy_regime_confidence, spy_regime_conflict)
trend.stock_*     (SMA fields, slopes, stacks, reclaim/loss, near-flags)
trend.spy_*       (SPY analogs)
trend.derived_*   (stock-vs-SPY explicit booleans)
momentum.*        (MACD fields + state)
compression_volatility.*  (TTM fields, BB fields, atr_percentile, semantic label)
execution.*       (planned_entry, actual_next_open, planned_stop, planned_target, planned_1R, entry_gap_flag)
outcome.*         (assigned by resolver: outcome, r_multiple*, mae, mfe)
```
Namespacing is a naming convention within the flat dict — no nested structure
required for CSV export.

## Orthogonal + interaction cells (v0.3)

Orthogonal cells for BIDC (each parented to `A1_generic_inside_day`):
```
B14_near_demand                    (inside demand zone OR nearest_demand_distance_atr ≤ 0.5)
B15_room_to_supply_R_ge_2          (room_to_supply_R ≥ 2)
B16_room_to_supply_R_ge_3          (room_to_supply_R ≥ 3)
B17_spy_outperforming              (rs_class == OUTPERFORMING)
B18_spy_trend_up                   (spy_trend_component in {UPTREND, STRONG_UPTREND})
B19_positive_rs_during_spy_weakness (rs_during_spy_weakness_frac_outperformed ≥ 0.6)
B20_price_above_rising_sma50       (above_sma50 AND sma50_slope class == RISING)
B21_bullish_sma_stack              (bullish_full_stack)
B22_recent_sma50_reclaim           (0 ≤ bars_since_reclaim_sma50 ≤ 10)
B23_macd_bullish_expanding         (macd_state == BULLISH_EXPANDING)
B24_ttm_bullish_release            (bars_since_squeeze_release ≤ 5 AND squeeze_release_direction == "up")
B25_bb_expansion                   (bb_state == EXPANSION)
B26_bb_compression                 (bb_state == COMPRESSION)
```

Interaction cells (**frozen preregistered list**, all parented to
`A1_generic_inside_day`):
```
I1_spy_trend_up_AND_stock_outperforming
I2_stock_sma50_rising_AND_spy_sma50_flat_or_falling
I3_room_to_supply_R_ge_2_AND_positive_momentum
I4_ttm_release_AND_bb_expansion
```
No cell may be added post-hoc after inspecting results. Adding one bumps the
preregistration version.

## Statistical reporting (v0.3)
Every cell reports the v0.2 columns plus:
```
resolved_n                (= n_scoreable)
expectancy_R              (mean_R_primary — kept for terminology alignment)
median_R
total_R                   (sum of r_multiple on scoreable rows)
gap_rate                  (n_gap_stop + n_gap_target) / n_total
expectancy_R_ci_low       bootstrap 95% CI lower (percentile method, 1000 resamples)
expectancy_R_ci_high      bootstrap 95% CI upper
win_rate_ci_low           bootstrap 95% CI lower for primary_2R_pct
win_rate_ci_high          bootstrap 95% CI upper
```
Bootstrap is deterministic given a per-run seed derived from `run_id`.
CI columns are `NaN` when `n_scoreable < 30`.

Uncertainty is a first-class column. **No cell may be called an edge based on
a point estimate alone.**

## Stability surfaces (v0.3 preregistered breakpoints)
For continuous features, report the same stats across preregistered
breakpoints. **The report never automatically picks the best-performing
breakpoint.**

```
room_to_supply_R:      ≥1.0, ≥1.5, ≥2.0, ≥2.5, ≥3.0
sma_distance_atr:      ≤0.25, ≤0.50, ≤1.0, >1.0
sma_slope class:       FALLING, FLAT, RISING (three-way)
rs_spy_20d:            ≤−5%, (−5%,+5%), ≥+5%
bb_width_percentile:   ≤10, ≤20, ≤30, ≤50
```

## Causal guarantees (v0.3)
- Every context module is tested for **prefix-replay invariance**
  (compute at T using `df[:T+1]` == compute at T using `df[:T+K+1]` where K > 0).
- Every context module is tested for **append-future invariance**
  (features at T are identical whether or not bars > T exist).
- No forward-fill through market-data gaps as though SPY traded normally.
  Stock/SPY alignment is via `pd.merge_asof(direction='backward',
  tolerance=1 day)` for daily bars; documented in `research/relative_strength.py`.
- Higher-timeframe values (when they land) must come from the last
  **completed** HTF bar whose `close_timestamp ≤ T`. Currently open (unfinished)
  HTF bars are a causality violation.

## Feature provenance (v0.3)
Each feature block records:
```
_feature_version         (semver of the layer's code — bumped on math change)
_source_timeframe        ("1d" for phase 1; "1h", "4h" for phase 2)
_source_data_end         (timestamp of last bar consulted)
_known_at                (timestamp at which the feature was knowable)
```
For structural objects (zones, levels): also `source_bar` + `known_at_bar`.

## Research ledger (v0.3)
Every `research/results/<run>/manifest.json` includes:
```
git_commit
preregistration_version
detector_version
resolver_version
feature_versions          (dict per layer)
dataset_hash              (sha256 of concatenated per-symbol OHLC digests)
config_hash               (sha256 of the CLI args + preregistered thresholds)
run_id                    (uuid4)
run_timestamp
```

## Non-goals in this phase
- No promotion to Top 10 / Telegram.
- No changes to production scoring, alerts, entries, ranking weights, or trade eligibility.
- No threshold tuning to hit an R target.
- No composite / confluence score.
- No point counters ("+1 for above-SMA50, +1 for MACD bullish").
- No weighted blend of layers ("0.3·regime + 0.2·MACD + …").
- No wiring of `research/` into `src/`.
- No implementation of detectors 2–5 (spec-only in this preregistration).
- No promotion of any context feature to "signal" status. All features remain
  observables to be measured, not asserted edges.

## Changelog

### v0.3 — 2026-09-16 — Context Layer / Research Integrity Expansion

**New layers, all read-only research modules, none wired to production**:
- Supply/demand zones with explicit provenance, freshness, invalidation, and
  distance/room-to-opposing fields.
- Multi-lookback relative strength vs SPY, including RS during SPY
  weakness/strength and structural divergence booleans.
- SPY regime **components** exposed (trend + risk axes + confidence + conflict
  flag) alongside the canonical semantic label.
- SMA trend structure (20/50/100/200) — distance (pct + ATR), slope with
  normalized calc + FALLING/FLAT/RISING classification, stack booleans,
  reclaim/loss bars-since events, nearest-SMA proximity, stock-vs-SPY
  comparison.
- MACD momentum with raw fields, slopes, acceleration, cross tracking, and
  BULLISH_EXPANDING / BULLISH_FADING / … state.
- TTM squeeze with exact preregistered math (BB inside Keltner, 20-bar
  linear-regression momentum) + squeeze-duration + release direction.
- Extended Bollinger with %B, midline/width slopes, expansion/contraction
  booleans + COMPRESSION/EXPANSION/NORMAL state.
- Volatility/compression semantic label (DEEP_COMPRESSION / COMPRESSION /
  NORMAL / EXPANDING / HIGH_VOLATILITY) — description, not score.

**Statistical reporting** — bootstrap 95% CIs for expectancy_R and win_rate
(1000 resamples, deterministic seed), expectancy_R / total_R / median_R,
gap_rate. CIs NaN below n_scoreable=30.

**Stability surfaces** — preregistered breakpoints per continuous feature.
Report never auto-selects the best-performing bucket.

**Orthogonal + interaction cells** — 13 new orthogonal single-modifier
cells (B14–B26) and 4 frozen interaction cells (I1–I4). Adding cells
post-hoc = version bump.

**Causal guarantees** — universal prefix-replay + append-future invariance
tests. Higher-timeframe rule: last-completed-bar only. Stock/SPY alignment
via merge_asof with 1-day tolerance, no forward-fill through gaps.

**Research ledger** — git_commit / preregistration_version / detector_version
/ resolver_version / feature_versions / dataset_hash / config_hash / run_id
/ run_timestamp on every run's manifest.

**Non-goals reinforced** — no composite score, no per-condition point
counters, no weighted-layer blends.

**Guardrails addendum (2026-09-16 same-day revision):**
- **Mathematical definitions** — every previously subjective term (base,
  departure, pivot, repeated rejection, zone width, creation, known_at,
  touch, freshness, invalidation, SMA slope class, reclaim, loss, near,
  MACD state neutral band, TTM squeeze, BB compression) pinned to numeric
  predicates in `## Mathematical definitions of subjective terms`.
- **Historical regime reconstruction** — every occurrence's SPY regime
  is computed from SPY bars ≤ t only. No current snapshots attached to
  historical setups.
- **Minimum observation rules** — enumerated in `## Minimum observation
  rules (v0.3)`. Below the minimum, a feature returns `UNAVAILABLE`, never
  a neutral default. `rs_during_spy_weakness_*` requires ≥ 10 qualifying
  SPY weakness bars; `momentum.macd_*` requires ≥ 38 bars; `compression_volatility.ttm_*`
  requires ≥ 40 bars; `trend.stock_sma_200` requires ≥ 200 bars; etc.
- **Correlated feature families** — the eight families enumerated in
  `## Correlated feature families (v0.3)` are stored as separate raw
  observables but MUST NOT be treated as independent confirmations.
  Interaction cells that combine same-family members are labeled
  `redundant_by_construction`.
- **Missing ≠ neutral** — every field's missing-value policy is one of
  `UNAVAILABLE` (input absent / below minimum) or `UNKNOWN` (input present
  but rules did not resolve). Never coerced to `NEUTRAL`, `FLAT`, `False`,
  `0`, or `no-signal`. Report renders `n_UNAVAILABLE` and `n_UNKNOWN`
  alongside `n_TRUE` / `n_FALSE`.
- **Bounded scope reaffirmed** — no detectors 2–5 implementation, no
  production wiring, no threshold tuning against results, no automatic
  best-feature ranking, no composite.

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
