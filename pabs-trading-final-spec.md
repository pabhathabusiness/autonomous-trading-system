# pabs.trading — Final Spec (adapted to live schema, v2)

Grounded in EXTRACT_FOR_SPEC.md facts: `direction` exists (64L/14S) · outcome is NOT a grade input ·
legacy trades CANNOT receive true letter grades (archetype/dim_scores/rs_vs_spy unrecoverable) ·
r_multiple backfill math verified against SRPT · `proposals` has no `direction` column ·
`close_on_live_cross` has no timeout branch (only `resolve_open` does).

Objective function for everything here: **maximize expectancy (avg R), monitor win rate, never target it.**

---

## LANE 1 — Backfills (pure data, zero risk, do first)

### 1.1 r_multiple: 10/78 → 78/78
Use the verified formula from §3c, direction-aware:

```sql
-- risk% = |entry - stop| / entry * 100
UPDATE paper_trades
SET r_multiple = ROUND(return_pct / (ABS(entry - stop) / entry * 100), 2)
WHERE status = 'closed'
  AND r_multiple IS NULL
  AND return_pct IS NOT NULL
  AND ABS(entry - stop) > 0;
```

`return_pct` is already direction-signed (MAXN short shows -15.0% on an adverse move), so no
sign flip needed here — but VERIFY on one short before running: pick a closed short winner and
confirm computed R is positive. Validation gate: SRPT must produce +1.40R, MAXN must produce -1.00R.
Snapshot the table first (`CREATE TABLE paper_trades_bak_20260711 AS SELECT * FROM paper_trades`).

### 1.2 exit_reason (derived, new column — close functions untouched)
Mirror the exact stop/target branch logic pasted in §6:

```
ALTER TABLE paper_trades ADD COLUMN exit_reason TEXT;  -- 'stop'|'target'|'timeout'|'unknown'
```

Derivation per closed row, using the same comparison the close functions use (direction-aware):
- exit within tolerance of stop level → `stop`
- exit within tolerance of target → `target`
- closed by `resolve_open`'s timeout branch (age exceeded, price between levels) → `timeout`
- else → `unknown` (count these; if > ~10% something's off)

Note from §6: `close_on_live_cross` never times out, so any `timeout` row is attributable to
`resolve_open` — useful provenance for free.

### 1.3 MAE / MFE (new columns `mae_r`, `mfe_r`)
Daily OHLC between open and close date per trade. Long: `mae_r=(min(low)-entry)/|entry-stop|`,
`mfe_r=(max(high)-entry)/|entry-stop|`. Invert for shorts. This is the single highest-value
backfill for the notes system — it distinguishes "thesis wrong" (MFE never > 0.3R) from
"stop too tight" (MAE tagged stop, then price hit target).

### 1.4 Scanner-side fix
`proposals` lacks `direction`. Add it at proposal time (the scanner knows it — `downside`
setups are shorts). Until then any proposal-level analytics must JOIN to `paper_trades` to
recover direction; make that explicit in the loader.

---

## LANE 2 — Grading (two tracks, never blended)

### 2.1 Live track (exists — do not modify logic)
`grade_fields` → `process_grader.grade` at open, outcome-blind. Correct design; leave it.
Only additions: persist `market_regime` and `mtf_alignment` (Lane 4) into its inputs going
forward so future grades reflect them.

### 2.2 Retro track for the 78 legacy trades — "R-grades"
True grades are impossible (§3e). Instead compute a **retro-grade** from what IS recoverable:

| Component | Source | Weight |
|---|---|---|
| Quality score | proposal JOIN | 30 |
| Planned R:R | entry/stop/target, `clamp((rr-1.2)/1.8,0,1)` | 25 |
| Edge/confluence depth (family-collapsed, see 2.3) | proposal JOIN `edges` | 20 |
| Stop sanity | needs ATR backfill; until then use `risk% vs symbol's median daily range` from OHLC | 15 |
| Liquidity | ADV$ from OHLC history | 10 |

Score 0–100 → `A ≥ 85, B ≥ 72, C ≥ 58, D ≥ 45, F < 45`.

Output: `retro_grade` in a **new column**, displayed as `R-A`, `R-B`... with a distinct badge
style (outline instead of filled). Stat cards get a toggle: `Graded (live) | Retro | Combined`,
default = live-only, so the real process-grade stats are never contaminated. The `L` chip on
the dashboard is replaced by the retro badge once backfilled.

### 2.3 Confluence family collapse (fix in scanner scoring, affects future grades)
Group flags into families before counting depth:
squeeze_family (all `*_squeeze` → 1 + 0.25/extra TF, cap 1.5) · structure_family
(flat_price/accumulation/base_intact) · momentum_family (rsi_room etc.) · relative_family
(rs_vs_spy etc.). AIG's 7 flags ≈ 3 families. Apply to the coil-score line found in EXTRACT §4 —
this changes future quality scores; keep the old score stored alongside (`quality_raw`)
for before/after comparison.

### 2.4 Quadrants (all closed trades, both tracks)
process/retro grade ≥ B × outcome → `skill_win | lucky_win | good_loss | bad_loss`.
`lucky_win` is the headline defect view.

---

## LANE 3 — Trade Thesis Notes ("would YOU take this trade?")

Every proposal and every closed trade gets a structured thesis, rendered in the detail panel —
code computes the verdict, LLM writes only prose.

```json
{
  "verdict": "take" | "pass" | "take_reduced",
  "conviction": 1-5,
  "why_take": ["...specific, cites numbers..."],
  "why_not": ["...specific, cites numbers..."],
  "structure": {
    "band": "position (3-8w expected)",
    "trigger": "breakout > 80.93",
    "invalidation": "close < 71.97 OR weekly squeeze fires opposite direction",
    "management": "no adds; trail to breakeven at +1R; time-stop at 8w"
  },
  "risk_verdict": "take_reduced — earnings proximity caps size at half",
  "kill_criteria": ["MFE < 0.3R after 2 weeks = thesis stale, exit flat"]
}
```

Verdict logic (deterministic): `pass` if any hard filter from learnings.json fires, or MTF
coherence fails (Lane 4), or R:R below band floor (band floors: scalp 1.5, swing 1.8,
position 2.0, long 2.2). `take_reduced` if exactly one soft caution. Else `take`.
A `pass` must name the specific rule, never a vibe.

Closed trades get a **post-mortem appendix**: MAE/MFE vs plan, exit_reason vs intended exit,
what the thesis got right/wrong, and (if a pattern) a `proposed_rule` for learnings.json.
Promotion rule: candidate → active only at n ≥ 8 with consistent avg-R sign;
auto-demote on forward flip. Expectancy is the fitness metric, not win rate.

---

## LANE 4 — Multi-timeframe coherence + Market Bias layer

### 4.1 Per-symbol MTF bias
Compute bias with ONE shared method on weekly / daily / 4h / 1h: price vs 20EMA + EMA slope
+ higher-high/higher-low structure → `bullish | bearish | neutral` per TF, all computed at the
same timestamp (stamp it — stale-data divergence must be detectable).

**Coherence gate:** a trade's direction must agree with its own band TF **and one TF above**
(swing = daily + weekly agree; position = weekly + monthly-proxy agree). Intraday TFs are
allowed to disagree — a short entered on an intraday bounce into resistance is *good* execution —
but the disagreement is displayed as a labeled chip, e.g. `MTF: W↓ D↓ 4h↑ (pullback entry)`.

If the thesis TF itself conflicts (bearish thesis, bullish daily+weekly): verdict → `pass`
unless the setup is explicitly counter-trend, and log every conflict with raw inputs to a
conflicts table for a 2-week review — if conflicts cluster on shorts, it's a sign bug in the
bias computation; fix the computation, not the display.

### 4.2 Weekly Market Bias panel — indexes + Mag 7
Weekly job (+ daily label refresh):
- **Indexes:** SPY, QQQ, IWM, DIA, RSP + the 11 SPDR sectors
- **Mag 7:** AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA

Per symbol: weekly bias (same method as 4.1), RS vs SPY, distance from 20w EMA, weekly squeeze
on/off. Roll up to `market_regime`:
`risk_on` (SPY+QQQ weekly bullish AND ≥4 Mag7 bullish) · `risk_off` (both bearish AND ≤2 Mag7
bullish) · `chop` otherwise. Store `market_regime` + `rs_vs_spy` on every new proposal
(new columns) so all future trades are fully gradable with zero gaps.

Effect on trades: longs in `risk_off` and shorts in `risk_on` get a quality penalty (-1.0)
and thesis caution; never a hard block until learnings data earns it (n ≥ 8 rule).

Dashboard: a bias strip above Trade Ideas — SPY/QQQ/IWM/DIA chips + Mag7 mini-grid
(green/red/grey per name) + regime label. Chips clickable → news drawer (see addendum).

---

## LANE 5 — Sort / filter / stat cards

Sortable (tri-state desc→asc→off, nulls last, shift-click secondary): date, symbol, setup,
band, rr, quality, grade (live+retro ordinal), r_multiple, return_pct, mae_r, mfe_r,
hold_days, exit_reason. Default Closed sort: `r_multiple DESC`.

Facets (multi-select chips, AND across groups, OR within): setup · direction · band · grade
(with track toggle) · quadrant · outcome · exit_reason · sector_name · market_regime ·
MTF-conflict flag · defect tags. Range sliders: R:R, quality, r_multiple, hold_days.

Preset views: **Best trades** (`r_multiple DESC`) · **Lucky wins** · **Repeat defects**
(group by defect tag, count desc) · **Regime mismatch** (longs in risk_off + shorts in risk_on).

Stat cards recompute on active filter, each shows `n`. Cards: Expectancy (avg R) ·
Profit factor · Process rate (% ≥ B, live track only) · Avg MAE on winners · Win rate
(labeled "monitored, not targeted").

Wire params into the /api/log/algo loader (EXTRACT §7) — additive, no breaking change.

---

## Build order
1. Lane 1.1–1.2 → 2. Lane 1.3 → 3. Lane 2.2 retro-grades → 4. Lane 5 → 5. Lane 4 →
6. Lane 3 + learnings.json → 7. Lane 2.3 confluence collapse LAST (changes scores; land
after baselines exist, keep quality_raw).

Every write in Lanes 1–2 goes to a new or currently-NULL column. Snapshot before Lane 1.
Full rollback = restore snapshot.
