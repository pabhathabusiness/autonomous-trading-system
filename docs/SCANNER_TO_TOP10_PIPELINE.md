# SCANNER -> TOP 10 PIPELINE SPEC

**DRAFT — for owner review, not wired to production.**

**Status:** Design (isolated, non-wired). Rev 2, revisions applied per critique.
**Companion docs:** `PLAYBOOK_v2.1.1.md`, `docs/TOP10_UX_SPEC.md`, `docs/MARKET_INTELLIGENCE_SCHEMA.md`.
**Scope:** the finite-state machine that carries a candidate from a raw scanner hit to a ranked slot on the Top 10 page.
**Non-scope:** ranker internals, frontend changes, production wire-up. The existing ranker is a **black box** called at exactly one transition; `src/static/index.html` and `src/static/app.js` are not touched.
**Owner rule of thumb:** the pipeline is a *stage machine over candidates*, not a scoring model.

---

## 1. Purpose

Describe how a candidate ticker moves from a raw scanner hit to a ranked slot on the Top 10 page so that:

1. Every trade-card field (all 14) has a documented producer stage.
2. `setup_hypothesis` is generated *independently* from `current_structure_bias` and the two are allowed to disagree.
3. `conditional_trade_side` is resolved by trigger evaluation at `TRIGGERED`, never preassigned.
4. Playbook gates (D-1..D-14) act as **branch off-ramps**, not silent filters — every skip is traceable.
5. The pipeline is idempotent per `(date, tick, inputs, evaluator_versions)` so replays produce identical Top 10 output.

---

## 2. Model

A **candidate** is the tuple `(date, symbol, setup_hypothesis_id, candidate_id)`. That tuple is the FSM's unit of state. A single symbol may host multiple candidates in one session (e.g. `AAPL` running `continuation` and `failed_breakout` in parallel); each has its own FSM instance and its own trade card. `candidate_id` is a monotonic per-session counter, tie-broken by `(date, symbol, hypothesis_kind_lex, ref_level)` on replay so parallel candidates are reproducible.

### 2.1 States (canonical enumeration)

| State | Meaning | On the UI |
|---|---|---|
| `DETECTED` | Scanner surfaced the symbol; no thesis yet. | Not shown. |
| `FORMING` | Setup hypothesis attached; evidence accumulating; trigger not armed. | Ideas band, low emphasis. |
| `READY` | Setup preconditions met; trigger armed and watching a specific price/volume event. | Ideas band, primary emphasis. |
| `TRIGGERED` | Trigger event fired; ranker scored the card; option expression selected. | Ideas band, numbered slot. |
| `BLOCKED` | Branch state. A playbook gate forbids progression. Enterable from any of `FORMING`, `READY`, `TRIGGERED`. Remembers exactly one `pre_block_state`. | Guardrail band with reason chip. |
| `EXPIRED` | Terminal. TTL elapsed, invalidation hit, day rolled, or thesis killed. | Not shown; retained for D-14 audit. |

There is **no `SLOTTED` state**. A card at `TRIGGERED` renders in a numbered Top 10 slot as UI derivation of `TRIGGERED` + `rank_score`. The prior draft's "TOP 10 SLOT" box is deleted; nothing transitions into it. Slot rendering is UI, not FSM state.

`TRIGGERED` is a one-way threshold: a candidate that reaches it never returns to a pre-trigger state (I5). Post-trigger management (position exits, stops) lives outside this FSM.

**"Live" defined.** A candidate is *live* iff its state ∈ `{FORMING, READY, TRIGGERED}`. `BLOCKED` is **not live**. `DETECTED` is live only for the purpose of T2/T3. TTL-based transitions (T3/T6/T9/T13) fire only against live candidates. `BLOCKED` uses T12 exclusively for TTL, and T14 for the post-trigger-blocked-then-day-boundary case.

### 2.2 State variables carried on every candidate

Two variables are the crux of this spec and are held **independently**:

- `current_structure_bias ∈ {bullish, bearish, mixed, unknown}` — the read of the ticker's market structure **right now**. Sourced from live MTF + RS-vs-SPY evaluation. Updates on every evidence tick that touches its inputs.
- `setup_hypothesis ∈ HypothesisKind` — the **thesis being tested**. Set once at `FORMING` entry (T2), mutated only by an explicit re-hypothesis transition (T5).

**`HypothesisKind` enum (side-agnostic).** Renamed from the prior draft to remove the side collapse the critique flagged. Every kind names *the structural test*, not a direction. Which side becomes the trade is decided at trigger fire.

| Kind | Test |
|---|---|
| `continuation` | Trend persists through the reference level. |
| `failed_breakout` | Level is briefly broken then rejected. |
| `mean_reversion` | Extension away from a reference reverses toward it. |
| `range_break` | Boundary of an established range gives way. |
| `gap_fade` | Gap fills back into prior range. |
| `compression_break` | A compression regime resolves in either direction. |
| `earnings_reaction` | Post-earnings drift or fade, D-7-eligible. |

Card field #1 mirrors `current_structure_bias`; card field #2 mirrors `setup_hypothesis` (kind + reference level). They MAY disagree, and the UI must render them adjacent.

Other variables held on the candidate:

- `conditional_side_map: {trigger_id -> side}` — e.g. `{"break_HOD": LONG, "reject_HOD": SHORT}`. Side is not preassigned; card field #3. Non-empty in `FORMING`, `READY`, `BLOCKED`.
- `armed_triggers: set<trigger_id>` — subset live in `READY`. Empty set in READY forces T8 decay to FORMING (see §5).
- `invalidation_level: price` — underlying level that kills the thesis; card field #6.
- `r_planned: float | null` — planned account loss in dollars if invalidation hits, `null` until T7.
- `blocks_active: set<rule_id>` — playbook rules currently forcing `BLOCKED`. Mutated in-place while `state == BLOCKED` (I6); this is not a state transition.
- `pre_block_state ∈ {FORMING, READY, TRIGGERED}` — where to return when the block lifts.
- `state_entered_at`, `evidence_last_at`, `ttl_remaining_ms` — timestamps driving TTL and freshness.

### 2.3 Invariants

- **I1:** `current_structure_bias` may change in any state without changing `setup_hypothesis`.
- **I2:** `setup_hypothesis` changes only via T5, and only from `FORMING`.
- **I3:** `conditional_side_map` is non-empty in `FORMING`, `READY`, `BLOCKED`; collapses to a single resolved side in `TRIGGERED`.
- **I4:** The ranker is invoked on exactly one transition per candidate: T7. See §8 for what "invoked once per candidate" means when the ranker consumes the full `TRIGGERED` set.
- **I5:** A candidate that ever entered `TRIGGERED` never returns to a pre-trigger state. In particular, T11 from a `BLOCKED` whose `pre_block_state == TRIGGERED` restores to `TRIGGERED`, and this is the only permitted "return" (I5 refers to *pre-trigger* states — FORMING, READY, DETECTED).
- **I6:** `BLOCKED` remembers exactly one `pre_block_state`. Re-blocks while blocked mutate `blocks_active` **in place** without changing state or overwriting `pre_block_state`. This is not a transition; it is a side effect on a stateful field.
- **I7:** Every stage transition writes a `transition_row` before the new state is visible to any reader.
- **I8:** `hypothesis_generator` and `current_bias_classifier` share input features but produce structurally different outputs; §7 pins the independence contract with an operational test.

---

## 3. Pipeline diagram

BLOCKED and EXPIRED are drawn as first-class boxes, per the critique.

```
    +--------------------------+
    |  scanner-raw (external)  |
    +------------+-------------+
                 |
                 v (T1)
          +------+-------+
          |  DETECTED    |------------------+  (T3: no hypothesis / TTL)
          +------+-------+                  |
                 | (T2)                     |
                 v                          |
          +------+-------+  <---+ (T8       |
     +--->|  FORMING     |------+  decay)   |
     |    +------+-------+                  |
     |           | (T4)                     |
     |           v                          |
     |    +------+-------+                  |
     |    |   READY      |                  |
     |    +--+----+---+--+                  |
     |       |    |   | (T7)                |
     |       |    |   v                     |
     |       |    | +-+------------+        |
     |       |    | | TRIGGERED    |        |
     |       |    | +-+---+--------+        |
     |       |    |   |   |                 |
     |(T8)   |(T9)|   |(T13) (T10 late)     |
     |       |    |   |   |                 |
     +-------+    |   |   |                 |
                  |   |   v                 v
                  |   | +-+-----------------+---+
                  |   +-|      BLOCKED          |
                  |     +--+---------+----------+
                  |        |         |
                  |        | (T11)   | (T12 / T14)
                  |        v         v
                  |    pre_block_state    +-----------+
                  +--------------------+->|  EXPIRED  |
                                          +-----------+

  T5: FORMING -> FORMING (self-loop, re-hypothesis; same candidate_id).
  T10: FORMING | READY | TRIGGERED -> BLOCKED (any live state, gate-specific).
  T6:  FORMING -> EXPIRED (TTL / pre-ready invalidation).
```

The FSM is monotonic forward under normal flow. Two backward edges exist:

- **T8: READY -> FORMING** — decay. Reversible if evidence returns before FORMING TTL.
- **T11: BLOCKED -> pre_block_state** — the block cleared.

Deeper demotion (FORMING -> DETECTED) is not supported.

---

## 4. Evidence sources

Every transition names its evidence source. Sources produce ticks; ticks are the only inputs evaluators consume.

| Source | Produces | Idempotency rank (for tie-break) |
|---|---|---|
| `scanner` | Raw hits. | 1 |
| `regime` | SPY regime (BULLISH / BEARISH / MIXED). | 2 |
| `book` | Open positions and their planned R. | 3 |
| `cluster` | Correlation-cluster membership (r ≥ 0.6). | 4 |
| `earnings_cal` | Upcoming/past earnings; blackout state. | 5 |
| `mtf` | 1m / 5m / 1H / 1D bias per timeframe. | 6 |
| `rs` | Relative-strength score and direction vs SPY. | 7 |
| `zones` | Supply/demand zones; next-level distance. | 8 |
| `compression` | Bollinger squeeze / ATR contraction flag; width-percentile. | 9 |
| `momentum` | Breakout, gap, earnings-reaction flags. | 10 |
| `clock` | Wall time; TTL and day-boundary only. | 11 |

**Tie-break rule (pinned).** Ticks with equal `tick_ts` are processed in ascending `idempotency rank`. Within a source, `seq` breaks further ties. This is the total order the replayer uses (§12).

**Timezone (pinned).** All `tick_ts` values are UTC. The 16:00 ET session boundary is emitted by `clock` as a UTC tick derived from the New York calendar (America/New_York), including DST. Sources that submit local timestamps are normalized to UTC at ingest before entering the tick order.

**`evidence_last_at` update rule (pinned).** `evidence_last_at` refreshes on any tick from `{mtf, rs, zones, compression, momentum, scanner}` that changes at least one card field or its underlying variable. Ticks from `{book, cluster, regime, earnings_cal, clock}` do **not** refresh freshness — their role is gating, not setup evidence.

Evaluators are pure functions of `(state, state_variables, evidence_tick, evaluator_versions)`. Evaluators never read wall time internally; `clock` events arrive as ticks.

---

## 5. Transition table

Every row is a legal edge. Any transition not listed is illegal. Preconditions are conjunctive.

| # | From | To | Precondition | Evidence | Side effect on card |
|---|---|---|---|---|---|
| T1 | ∅ | `DETECTED` | Scanner emits a hit (deduped per §6.1). | `scanner` | Create candidate; #14 = fresh. |
| T2 | `DETECTED` | `FORMING` | MTF matrix populated to threshold §6.2.1; a hypothesis kind matches per §6.2.2 ordering. | `mtf`, `rs`, `zones` | Fill #1, #2, #3 (side map), #6, #7, #8, #9, #12; #4 = FORMING. |
| T3 | `DETECTED` | `EXPIRED` | No hypothesis matches within DETECTED TTL (5 min). | `scanner`, `clock` | #4 = EXPIRED; D-14 write. |
| T4 | `FORMING` | `READY` | All FORMING setup preconditions per §6.3.1 hypothesis-kind table met; ≥1 trigger armable. | `compression`, `momentum`, `zones` | #4 = READY; #10, #11 filled; `armed_triggers` populated. |
| T5 | `FORMING` | `FORMING` (self-loop) | Structural-impossibility test §6.3.2 fires for the current hypothesis. | `mtf`, `rs`, `zones`, `momentum` | Replace #2 and #3; same `candidate_id`; `state_entered_at` reset. |
| T6 | `FORMING` | `EXPIRED` | FORMING TTL elapsed OR invalidation breached pre-ready. | `clock`, `zones` | #4 = EXPIRED; D-14 write. |
| T7 | `READY` | `TRIGGERED` | ≥1 armed trigger fires §6.5.1 AND all applicable D-gates clear at fire tick §11.2. | `momentum`, `zones`, `regime`, `book`, `cluster`, `earnings_cal` | #3 collapses to fired side; **ranker called**; option expression selected; `r_planned` set; #4 = TRIGGERED. |
| T8 | `READY` | `FORMING` | Decay conditions §6.4.1 fire (compression relaxes to width-pct > threshold, volume < threshold, OR `armed_triggers` becomes ∅). | `compression`, `momentum`, `clock` | #4 = FORMING; #10 flips; `armed_triggers` cleared; #14 may age. `decay_event` row. |
| T9 | `READY` | `EXPIRED` | READY TTL elapsed OR invalidation breached OR day boundary. | `clock`, `zones` | #4 = EXPIRED; D-14 write with distance-to-trigger. |
| T10 | live | `BLOCKED` | Any D-rule applicable at current state (§11.2) evaluates to a block. | rule-specific | Snapshot `pre_block_state = <current>` (only if not already BLOCKED); add rule to `blocks_active`; freeze `ttl_remaining_ms`; #4 = BLOCKED. |
| T10b | `BLOCKED` | `BLOCKED` (in-place mutation, **not** a state transition) | A second rule fires while already blocked. | rule-specific | Add rule to `blocks_active`. No `transition_row`. `mutation_row` written for audit. |
| T11 | `BLOCKED` | `pre_block_state` | `blocks_active == ∅`. | rule-specific clearers | Restore #4; unfreeze TTL; drop chip. `state_entered_at` **is not reset** unless `pre_block_state == READY` and re-arming ticks fired during the block (§10.3). |
| T12 | `BLOCKED` (pre ∈ FORMING, READY) | `EXPIRED` | Frozen `ttl_remaining_ms` counted against wall time exceeds pre-block TTL budget, OR day boundary. | `clock` | #4 = EXPIRED; D-14 write with block reason. |
| T13 | `TRIGGERED` | `EXPIRED` | Position closed (per §6.5.3), invalidation hit post-trigger, or day rolled. | `book`, `clock`, `zones` | #4 = EXPIRED; **no D-14 write** — a taken trade. |
| T14 | `BLOCKED` (pre == TRIGGERED) | `EXPIRED` | Day boundary or invalidation while blocked post-trigger. | `clock`, `zones` | #4 = EXPIRED; **no D-14 write** — trade was already taken. This is the transition prior text called "T13 via BLOCKED"; naming it explicitly resolves the contradiction. |

**T7-diverted-to-BLOCKED.** If a trigger fires from `READY` but any applicable D-gate fails at that fire tick, the candidate takes T10 (from `READY`), not T7. This is a distinct D-14 skip class (`t7_diverted_block`) recorded in §13.

---

## 6. Stage detail

### 6.1 scanner-raw (external)

**In:** external rows: `ticker`, `scanner_id`, `hit_reason`, `hit_price`, `hit_ts`.
**Dedup key:** `(ticker, scanner_id, hit_ts_bucket)`, where `hit_ts_bucket` = `floor(hit_ts_utc_seconds / 60)`. Bucket size is 60 s; edges are half-open `[t, t+60)`. Two hits in the same bucket dedupe to the first-arriving; ties within the bucket order by source `seq`.
**Out:** deduplicated hits.
**Contract:** no interpretation.

### 6.2 DETECTED

#### 6.2.1 MTF populated threshold

T2 requires MTF for **1H and 1D** non-null. `5m` and `1m` may be `pending`; they will be filled during FORMING. A row lacking 1H/1D remains in DETECTED and either fills, expires (T3), or is picked up by a later `mtf` tick.

#### 6.2.2 Hypothesis matching order (deterministic)

`hypothesis_generator` iterates the enum in this fixed lexical order and returns the **first** matching kind:

`compression_break`, `continuation`, `earnings_reaction`, `failed_breakout`, `gap_fade`, `mean_reversion`, `range_break`.

Match predicates (per kind) are pure functions of `(mtf, rs, zones, compression, momentum, earnings_cal, scanner_row)`. **Exactly one candidate is created per T2 fire.** Symbols with genuinely distinct simultaneous theses (e.g. `continuation` and `failed_breakout` both plausible) surface the second thesis only via a subsequent scanner hit or a T5 re-hypothesis on the first candidate — never as a same-tick fan-out.

**Evaluators run:**
- `current_bias_classifier(ticker_ctx)` → `bullish | bearish | mixed | unknown`.
- `hypothesis_generator(scanner_row, ticker_ctx)` → hypothesis kind + reference level.
- `freshness_init(hit_ts)` → age = 0.

**Card fields at exit:** #1, #2, #14; provisional #8.

### 6.3 FORMING

#### 6.3.1 Per-hypothesis setup preconditions (T4 armability)

| Kind | T4 preconditions |
|---|---|
| `continuation` | Compression width-pct ≤ 25; MTF-higher aligned with hypothesis reference direction; RS \|z\| ≥ 1. |
| `failed_breakout` | Price within 0.5R of reference level; compression width-pct ≤ 40; a prior test of that level within the session. |
| `mean_reversion` | Distance from reference ≥ 1.5 ATR(20); no MTF-higher trend acceleration on the most recent bar. |
| `range_break` | Range defined (≥ 8 bars); price within 0.3R of a boundary. |
| `gap_fade` | Gap magnitude ≥ 0.75 ATR(20); prior-range boundary within 0.5R of price. |
| `compression_break` | Compression width-pct ≤ 15; no directional bar closes outside band in the last 3 bars. |
| `earnings_reaction` | Within 1 session of earnings print; volume ≥ 1.5× 20d-avg. |

Numeric thresholds are versioned with `evaluator_versions.forming_precondition_table` and pinned per §12.

#### 6.3.2 Structural-impossibility test (T5)

`hypothesis_impossibility(hypothesis, ticker_ctx)` returns `impossible` iff **all** of the following hold on the most recent tick:

- The reference level has been decisively violated in the direction opposite the hypothesis test (close beyond level ± 0.5 ATR, on ≥ 1.5× volume).
- MTF-higher timeframe alignment has flipped (1H bias reversal or 1D bias reversal).
- The kind-specific `structural_kill_test` (per §6.3.2 table below) returns true.

| Kind | `structural_kill_test` |
|---|---|
| `continuation` | Trendline break confirmed on 1H close. |
| `failed_breakout` | Level held on retest with volume expansion. |
| `mean_reversion` | Impulse continues (bar 4 makes new extreme). |
| `range_break` | Range boundary broke and held; no return. |
| `gap_fade` | Gap holds through 2× ATR excursion. |
| `compression_break` | Volatility expansion resolved with 3+ bar follow-through. |
| `earnings_reaction` | Drift reverses on same-day; secondary catalyst confirmed. |

When `impossible` fires, `hypothesis_generator` is re-invoked on the current context; if a different kind matches (in the §6.2.2 order), T5 fires. If none matches, the candidate stays in FORMING; if FORMING TTL expires, T6.

**Evaluators run in FORMING:** `sd_zone_finder`, `compression_scorer`, `momentum_event_tagger`, `mtf_aligner`, `rs_vs_spy`, `earnings_state`, `conditional_side_authoring(hypothesis, ctx)`, `trigger_writer`, `invalidation_writer`.

**Completion marker:** every card field populated AND at least one trigger authored.

### 6.4 READY

#### 6.4.1 Decay conditions (T8)

T8 fires if any of:

- Compression width-pct crosses above 40 (was ≤ 25 or ≤ 15 at T4).
- Volume rate over the last 3 bars falls below 0.7× 20d-avg.
- `armed_triggers == ∅` after partial disarms.
- Freshness bin transitions to `stale` (evidence_last_at > 15 min).

**Partial disarm.** If one of several `armed_triggers` disarms but the set is still non-empty, the candidate remains in `READY` with a reduced set. T8 fires only when the set empties or when a decay condition above hits. This resolves the critique's partial-vs-total ambiguity.

**Evaluators:** `readiness_evaluator(card, live_ctx)`, `invalidation_watcher(card, tick)`.

**Completion marker:** `#4 == READY` AND `readiness_evaluator` passes on the most recent tick.

### 6.5 TRIGGERED

#### 6.5.1 Trigger fire ordering (tie-break)

If multiple `armed_triggers` cross their thresholds on the same tick, the resolved side is the trigger with the **smallest lexical `trigger_id`**. `trigger_writer` assigns ids in a canonical form (`{kind}_{level}_{side}`), so ordering is stable and replay-safe.

#### 6.5.2 Snapshot atomicity

`snapshot_at_trigger` is taken **synchronously** on the trigger tick, before any subsequent concurrent evidence is applied. The snapshot's schema is defined in §8.1 and is a *subset* of the existing ranker input, not a superset. Fields the existing ranker does not read are held on the candidate row but not passed in.

#### 6.5.3 Position-state detection (T13)

The FSM does **not** own position state. `book` publishes `position_event ∈ {opened, filled_partial, filled_full, closed, assigned}`. T13 fires on `closed` or `assigned` for the option leg tied to this candidate (via `candidate_id -> position_id` mapping recorded on the T7 row). `filled_partial` does not fire T13.

**Evaluators run:** `trigger_evaluator`, applicable D-gates re-run per §11.2, `invalidation_watcher`.

---

## 7. `setup_hypothesis` vs `current_structure_bias` — normative

This is the section the owner explicitly asked to make first-class. It is normative, not illustrative.

**Rule.** `current_structure_bias` and `setup_hypothesis` are produced by two different evaluators and **MUST NOT** be derived from one another.

**Independence contract (I8, operational).**

1. `current_bias_classifier` consumes only structural features (close vs sma20/sma50, ret_5d, sma50_slope) and returns one of `{bullish, bearish, mixed, unknown}`. Its output is a partition over recent tape shape.
2. `hypothesis_generator` consumes structural features **plus** `scanner_row` (the specific triggering event) **plus** `zones` (reference levels). Its output is a partition over *tests* one might run against the tape. Two distinct outputs from the same bias input are legal and expected.
3. **Test:** for every pair `(bias, kind)` in the Cartesian product, at least one historical evidence combination must exist that produces it, or the pair is declared unreachable in the versioned `bias_hypothesis_reachability_matrix`. Bumping the matrix is an `evaluator_versions` change.
4. Hypothesis kinds are **side-agnostic**. The prior draft's `long_continuation` / `short_failure` / `mean_revert_long|short` / `breakout_long` / `breakdown_short` names are eliminated. A `continuation` hypothesis against a bullish bias produces a side map like `{break_HOD_with_vol: LONG, reject_HOD_close_under: SHORT}` — the map is authored by `conditional_side_authoring` and always includes at least one trigger for each of the plausible sides that a hypothesis of that kind admits.

**Hypothesis-kind expected relationship to current bias (advisory, not enforced).**

| Kind | Typical bias relationship | Enforced? |
|---|---|---|
| `continuation` | Agrees. | No — bias may flip mid-life without killing the hypothesis; T5 fires only when the *structural* kill test triggers. |
| `failed_breakout` | Against. | No. |
| `mean_reversion` | Against extreme. | No. |
| `gap_fade` | Against gap direction. | No. |
| `range_break` | Bias-agnostic. | No. |
| `compression_break` | Bias-agnostic. | No. |
| `earnings_reaction` | Bias-agnostic. | No. |

**Consequence.** The relationship column is *typical*, not definitional. Downstream evaluators must not treat it as a constraint. The independence contract makes this operational, not aspirational.

**Worked mini-example (agreement) and disagreement-primary case are in §14** — the primary end-to-end example (§14.1) now walks a **disagreement** case, per the critique.

---

## 8. Ranker integration

### 8.1 Contract

The existing ranker is a black box:

```
rank_scores = existing_ranker(triggered_set_snapshot)
```

- **Call semantics (fixed).** The ranker is invoked **once per T7 fire**, receiving the full current set of `TRIGGERED` candidates as one call. I4 is refined: "invoked on exactly one transition per candidate" means each candidate contributes to exactly one T7 fire, but the call itself operates on a set. Rank scores of previously TRIGGERED candidates **may be revised** on that call. This is a deliberate property of the existing ranker; the pipeline preserves it and the D-14 log's `rank_score` column captures whichever value the ranker returned on this call for that candidate.
- **Input schema.** `snapshot_at_trigger` is defined as the exact tuple the existing ranker already consumes today, plus no new fields. The pipeline may **hold** the new fields on the candidate row (setup_hypothesis, conditional_side_map, invalidation_level, r_planned, blocks_active), but only the pre-existing subset is passed. If the owner later opts to extend the ranker's input, that is a separate versioned change; the spec forbids doing it silently here.
- **What the ranker is not asked to do.** Not asked to re-check playbook gates, not asked to reproduce hypothesis/bias split, not asked to filter by regime. Pipeline responsibilities upstream.
- **Determinism.** The existing ranker's determinism on identical `triggered_set_snapshot` is a **precondition** of §12, not an axiom. If a future audit shows non-determinism, §12's idempotency claim degrades and the D-14 replay must be re-baselined. This is stated so the assumption is visible.
- **Multi-candidate per symbol.** Two candidates for the same symbol both at `TRIGGERED` are both passed to the ranker. If the ranker dedupes by symbol internally, one is dropped; that dropping is a ranker property, not a pipeline decision. The pipeline **does not** collapse rows before the call.

### 8.2 Ideas-band ordering (explicitly outside the ranker)

`READY` and `FORMING` cards render on the Top 10 page's ideas band **without a rank number**. Their order is: `READY` before `FORMING`, then `state_entered_at` desc. This is **not** an extension of the ranker; it is a pipeline-side render ordering and is applied by the read path in the Top 10 UX layer described in `TOP10_UX_SPEC.md`. Documenting it here so it is not conflated with §8.1.

### 8.3 Open (deferred)

Q5 (collapse to one row per symbol on the Top 10 render) is a **UI reduction** and lives strictly downstream of the ranker call. If adopted, it is a filter over the ranker's output, never a rewrite of it.

---

## 9. Failure and decay

- **T8 READY -> FORMING.** Reason enumerated ∈ `{volume_decay, compression_expanded, all_triggers_disarmed, freshness_stale}`. Reversible. Writes `decay_event` row.
- **T9 READY -> EXPIRED.** Terminal.
- **T13 vs T14.** Post-trigger EXPIRED via `book` closure = T13. Post-trigger EXPIRED via day boundary or invalidation while `BLOCKED` = T14. Neither writes a D-14 skip; both write lifecycle rows for the position-outcome audit.
- **Late gate flip on TRIGGERED.** T10 fires from `TRIGGERED` to `BLOCKED`; frozen visually; managed outside FSM until T14 or T13.

No demotion below FORMING. If a setup degrades that far, EXPIRE and re-detect.

---

## 10. Time semantics

### 10.1 TTLs

| State | TTL | On expiry |
|---|---|---|
| `DETECTED` | 5 min. | T3. |
| `FORMING` | 90 min from `state_entered_at` **or** last evidence refresh, whichever is later. "Evidence refresh" = any tick that updates `evidence_last_at` per §4. | T6. |
| `READY` | 30 min from arm time. | T9. |
| `BLOCKED` | `ttl_remaining_ms` **is frozen** on T10 and unfrozen on T11. See §10.3. | T12 (pre ∈ FORMING/READY) or T14 (pre == TRIGGERED). |
| `TRIGGERED` | End of session. | T13. |

### 10.2 Day boundary

At 16:00 America/New_York (emitted as a UTC `clock` tick), all non-terminal candidates → `EXPIRED` via the applicable transition (T9 for READY, T6 for FORMING, T3 for DETECTED, T14 for BLOCKED-post-trigger, T13 for TRIGGERED, T12 for BLOCKED-pre-trigger).

### 10.3 BLOCKED and TTL — design decision

The prior draft said "BLOCKED does not extend the underlying life; the clock keeps running." This is reversed. **`ttl_remaining_ms` freezes on T10 and unfreezes on T11.** Rationale (design decision D-10.3): a transient regime blip (e.g. SPY dips into MIXED for 8 minutes then flips back BULLISH) should not burn the underlying setup's clock. The frozen-TTL policy matches the operator intuition that the setup's *life* is measured in setup-relevant time, not gate-blocked wall time. This resolves the numerical inconsistency the critique flagged in §14.

**Arm time and re-arm.** `state_entered_at` for READY is the T4 tick. It is **not** reset by T11 restoration unless the readiness re-evaluation on T11 required arming ticks that arrived during the block (indicating the original arm has decayed). In practice: if T11 restores to READY and `armed_triggers` is still non-empty, `state_entered_at` is preserved; if `armed_triggers` was cleared during the block, T11 must first pass through T8 semantics and the candidate lands in FORMING, not READY.

### 10.4 Freshness (card field #14)

- `fresh`: `now - evidence_last_at < 5 min`.
- `aging`: 5–15 min.
- `stale`: > 15 min. `stale` in `READY` forces T8 to `FORMING`.

Sources refreshing `evidence_last_at` are those enumerated in §4 (`mtf`, `rs`, `zones`, `compression`, `momentum`, `scanner` on card-field change).

---

## 11. Playbook gate integration

### 11.1 Rule table

| Rule | Trigger | Evidence | Clears |
|---|---|---|---|
| D-1 (options-first) | Applies **only at T7**. An equity-only expression emitted by the option-expression selector. | expression selector | Expression revised. |
| D-2 (two-layer required) | `setup_hypothesis` or `conditional_side_map` empty at T4 or later. | FSM self-check | Both populated. |
| D-3 (>2 concurrent) | `book` shows 2 open AND this candidate is READY or TRIGGERED. | `book` | A position closes. |
| D-4 (R < 2R) | Applies **only at T7**. `r_planned` at T7 below 2R min. | option expression | Expression revised or dropped. |
| D-5 (MIXED regime) | `regime == MIXED` AND **any side** in `conditional_side_map` (FORMING/READY) or the resolved side (TRIGGERED) is on the MIXED-restricted list. | `regime` | Regime flips OR side map narrows to unrestricted-only. |
| D-6 (cluster overlap) | Ticker's cluster (r ≥ 0.6) already has an open same-side position (evaluated against *every* side in `conditional_side_map` pre-trigger, resolved side post-trigger). | `cluster`, `book` | Overlapping position closes or map narrows. |
| D-7 (earnings blackout) | Earnings within blackout AND `setup_hypothesis != earnings_reaction`. | `earnings_cal` | Window passes or hypothesis is re-hypothesized to `earnings_reaction`. |
| D-8..D-13 | Per playbook. | rule-specific | rule-specific. |
| D-14 | Not a gate; log write-point — §13. | — | — |

### 11.2 Gate applicability by state (resolves the critique's D-1 / D-4 issue)

Not every gate is evaluable at every stage. This table pins where each fires.

| Gate | FORMING | READY | T7 (fire tick) | TRIGGERED (post) |
|---|---|---|---|---|
| D-1 | — | — | ✓ | — |
| D-2 | ✓ (self-check at T4 completion) | ✓ | ✓ (redundant, retained as safety) | — |
| D-3 | ✓ | ✓ | ✓ | ✓ (late flip → T10) |
| D-4 | — | — | ✓ | — |
| D-5 | ✓ (evaluated against side map) | ✓ | ✓ (evaluated against resolved side) | ✓ |
| D-6 | ✓ (side map) | ✓ | ✓ (resolved side) | ✓ |
| D-7 | ✓ | ✓ | ✓ | ✓ |
| D-8..D-13 | per rule | per rule | ✓ | per rule |

D-2's T7 re-check is retained as a safety trap for the case where a race between FORMING evaluators leaves the side map empty at read time; it is expected to be a no-op in the steady state.

### 11.3 BLOCKED semantics recap

- T10 adds rule to `blocks_active`, snapshots `pre_block_state` if not already blocked, freezes TTL.
- T10b (in-place mutation) adds another rule; no state change, no `pre_block_state` change.
- T11 fires only when `blocks_active == ∅`.
- T12 (pre ∈ FORMING, READY) or T14 (pre == TRIGGERED) fire on TTL exhaustion or day boundary.
- I5 is preserved: T11 with `pre_block_state == TRIGGERED` restores to TRIGGERED (not a pre-trigger state), which is legal.

---

## 12. Idempotency and reproducibility

**Claim.** For a fixed `(date, symbol, evaluator_versions)`, replaying the same day's evidence stream in canonical order produces the same terminal state, the same transition rows, and the same rank score.

**Guarantees:**

1. Every evaluator is deterministic given `(current_state, state_variables, evidence_tick, evaluator_versions)`. No wall-clock reads inside evaluators.
2. Every stage transition writes a `transition_row(candidate_id, from_state, to_state, tick_ts, reason, evaluator_versions)`.
3. **Canonical tick order:** primary sort `tick_ts` (UTC), secondary sort `source_rank` from §4 table, tertiary sort `seq` within source.
4. **Evaluator versions** live in a `pipeline_versions.json` checked into `research/`. On replay, the replayer refuses to run against a mismatched version file and prints the diff. Mixed-version replays are rejected, not silently reconciled.
5. Candidate store is append-only per `(candidate_id, tick_ts)`; demotions write new rows.
6. Ranker determinism on identical `triggered_set_snapshot` is a **precondition** (see §8.1). Violations are reported and re-baselined; they do not silently break replay.
7. T5 hypothesis-search order is fixed lexical (§6.2.2, same order as T2).
8. T2 fires **once per hit** and creates one candidate; no fan-out.
9. Day boundary is a `clock` tick, not a nondeterministic sweep.
10. Simultaneous trigger fires at T7 tie-break by smallest lexical `trigger_id` (§6.5.1).
11. Scanner dedup bucket is defined (60 s, half-open) — §6.1.

**Mid-session restart.** The candidate store is append-only. On process crash, the pipeline restart procedure is:

- Read the latest `transition_row` per `candidate_id` — that row's `to_state` is the last known state.
- Read the latest `mutation_row` per `candidate_id` in BLOCKED for `blocks_active` reconstruction.
- Re-subscribe to source feeds at the last-seen `(tick_ts, source, seq)` cursor; sources replay from their side.
- Any evaluator with a version mismatch since crash aborts rehydration for that candidate; it EXPIRES with cause `restart_version_skew` (D-14 write).

---

## 13. Instrumentation — D-14 skipped-opportunity log

| Event | Log row |
|---|---|
| T3 (DETECTED → EXPIRED, no hypothesis) | `date, symbol, cause=no_hypothesis, evidence_snapshot`. |
| T6 (FORMING → EXPIRED) | `date, symbol, hypothesis, cause={ttl|invalidation}, would_be_side_map`. |
| T9 (READY → EXPIRED) | `date, symbol, hypothesis, armed_triggers, cause, distance_to_trigger`. |
| T10 (any live → BLOCKED) | `date, symbol, hypothesis, stage_at_block, block_reason, full_card, would_have_ranked_at (nullable)`. |
| **T7-diverted (READY → BLOCKED at fire tick)** | `date, symbol, hypothesis, trigger_that_fired, gate_that_failed, full_card`. Distinct D-14 class. |
| T12 (BLOCKED[pre ∈ FORMING,READY] → EXPIRED) | `date, symbol, hypothesis, blocks_active, pre_block_state, cause=block_persisted`. |

**Not logged:**
- T13, T14 (taken trades).
- T8 (decay is reversible; `decay_event` row instead).
- T10b (accumulation, not a new skip).
- T11 (block cleared — still alive).

**Q3 resolution (design decision D-13.1):** T8 does **not** emit a D-14 row. Rationale: T8 is a reversible mid-life event; adding it inflates the skip log with non-terminal noise and undermines the weekly-review signal-to-noise. The `decay_event` row is queryable separately for oscillation analysis.

---

## 14. End-to-end worked lifecycles

### 14.1 Primary walkthrough — disagreement case (bias ≠ hypothesis)

Ticker `X`, 2026-09-16, session in UTC.

- **13:32:00Z T1.** Scanner hit: compression pending, `hit_price=102.40`. Prior high 102.35. `scanner.reason=compression_break_pending`.
- **13:34:15Z T2.** MTF: 1H bullish, 1D bullish. RS +1.4. `current_structure_bias = bullish`. `hypothesis_generator` order picks `failed_breakout` (matches: price within 0.5R of the 102.35 level, a prior test occurred at 12:58Z, compression tight). Side map authored: `{break_102.60_vol1.5x_hold2bar: LONG, print_above_102.60_reject_3bar_close_under_102.35: SHORT}`. Invalidation: 102.95 (structural higher-high that would confirm continuation and kill the short thesis; also kills the long side if it fails to hold the break). Bias `bullish`, hypothesis `failed_breakout`. Adjacent on the card. **Disagreement is the point.**
- **13:51:00Z T4.** Compression width-pct at 12 (≤ 40 for `failed_breakout`); both triggers armable. `armed_triggers = {break_102.60_vol1.5x_hold2bar, print_above_102.60_reject_3bar_close_under_102.35}`. READY. `state_entered_at = 13:51:00Z`. TTL 30 min → 14:21Z if unfrozen.
- **14:03:00Z T10 (D-5).** SPY regime tick: BULLISH → MIXED. LONG side of the map is restricted this session. Block. `blocks_active = {D-5}`. `pre_block_state = READY`. TTL freezes: `ttl_remaining_ms = 18 min`.
- **14:18:00Z T11.** Regime → BULLISH. `blocks_active = ∅`. Restore to READY. `armed_triggers` intact. TTL unfreezes: 18 min remaining → expires 14:36Z.
- **14:24:00Z T7.** Price prints 102.63 with vol 3.2× avg, closes above 102.60 on bar 1 and holds through bar 2. `break_102.60_vol1.5x_hold2bar` fires. Gate re-eval at fire tick: D-1 (option expression selected: `X 2026-10-16 102/104 call debit spread`, pass), D-3 (book 1 open, pass), D-4 (planned $500 loss, 2.3R, pass), D-5 (BULLISH, resolved side LONG, pass), D-6 (no cluster overlap, pass), D-7 (no earnings, pass), D-2 (side map non-empty, pass). Resolved LONG. Ranker called on `triggered_set_snapshot`; rank = 3. Card TRIGGERED, slot 3.
- **18:47:00Z T10 (D-3, late flip).** Third correlated position opens elsewhere. D-3 fires. `pre_block_state = TRIGGERED`. Frozen visually.
- **20:00:00Z T14.** Day boundary. BLOCKED[pre=TRIGGERED] → EXPIRED. No D-14 write (trade was taken). T14 row written.

**Terminal path:** DETECTED → FORMING → READY → BLOCKED → READY → TRIGGERED → BLOCKED → EXPIRED via T14. Numerical consistency check: 13:51 arm, 18 min TTL used (freezes at 14:03, unfreezes at 14:18), fires at 14:24 — 6 min after unfreeze, 12 min pre-block + 6 min post-block = 18 min consumed of 30. Within budget. ✓

### 14.2 T5 re-hypothesis lifecycle

Ticker `Y`, 15:00Z T2 fires with `continuation` (bias bullish, MTF-higher aligned, RS+). `state_entered_at = 15:00Z`. At 15:22Z a 1H bar closes decisively below the trendline (kill test for `continuation`), bias tick flips to `mixed`, `momentum` reports a rejection tag at the intraday high. Structural-impossibility fires. `hypothesis_generator` reruns; `failed_breakout` matches (a prior test now exists intraday). T5 self-loop. `candidate_id` unchanged. `setup_hypothesis` = `failed_breakout`. Side map replaced. `state_entered_at` reset to 15:22Z. FORMING TTL restarts. Card shows the flip; no new candidate row; existing D-14 skip log entries against the old hypothesis remain audit-attributed to the same `candidate_id`.

### 14.3 T8 decay-and-rearm cycle

Ticker `Z`, 14:10Z READY on `range_break`. At 14:19Z volume rate drops to 0.6× avg → T8. Reason: `volume_decay`. FORMING. `armed_triggers` cleared. `decay_event` row. At 14:31Z volume returns to 1.4× avg on a fresh compression signal; readiness re-evaluates; T4 fires. READY, new `state_entered_at = 14:31Z`, new arm. At 14:56Z price prints break; T7 fires; TRIGGERED.

Second-cycle variant: at 14:31Z the volume never returns; FORMING TTL (90 min from `state_entered_at`, which after T5-reset conventions is the original T2 timestamp; T8 does *not* reset FORMING's `state_entered_at`) elapses at 15:40Z; T6 → EXPIRED; D-14 row with `cause=ttl`, `hypothesis=range_break`, `would_be_side_map` recorded.

### 14.4 T3 example (DETECTED → EXPIRED, no hypothesis)

Ticker `Q`, 14:00Z scanner hit on `unusual_flow_alert`. MTF slow to fill (1D pending until 14:03Z). Between 14:00Z and 14:05Z, no hypothesis kind's match predicate returns true — the flow signature doesn't line up with any preregistered kind on this ticker's context. At 14:05Z the DETECTED TTL (5 min) elapses. T3 fires. D-14 row: `cause=no_hypothesis`, `evidence_snapshot={mtf: ..., rs: ..., scanner: ...}`. Illustrates a common quiet-day skip.

### 14.5 T6 example (FORMING pre-ready invalidation)

Ticker `W`, 14:20Z T2 to `failed_breakout` at reference 51.00, invalidation 51.55. Never reaches T4. At 14:41Z price prints 51.60 on volume expansion — invalidation breach in FORMING. T6 fires. D-14 row: `cause=invalidation, hypothesis=failed_breakout, would_be_side_map=...`. This is a "would-have-been-short" record.

---

## 15. What this spec is not

- Not a ranker redesign. §8.1 pins the input schema to the existing ranker contract.
- Not a frontend change. `src/static/index.html` and `src/static/app.js` untouched.
- Not a production wire-up. New modules are additive under `src/pipeline/` and `research/`, callable in isolation.
- Not a replacement for `PLAYBOOK_v2.1.1.md`. The playbook defines the gates; this spec places them in the FSM.
- Not a schema change to `/api/market/intel`.

---

## 16. Design decisions (where we kept the original against the critique)

- **D-10.3 (revised from original).** BLOCKED **freezes** the underlying TTL. Original said "clock keeps running"; we flipped it. Rationale: transient regime blips should not consume setup life; the §14.1 numbers only reconcile under freeze semantics.
- **D-13.1 (kept original).** T8 emits a `decay_event` row, **not** a D-14 skip row. Rationale: T8 is reversible; adding it to D-14 inflates the log with mid-life noise. The `decay_event` stream is queryable separately for oscillation analysis. Owner Q3 answered.
- **D-8.1 (kept original).** Ranker input schema is **not** widened to include new pipeline fields (setup_hypothesis, side_map, r_planned, etc.). Rationale: extending the black box is exactly the redesign the owner forbade. If a future rev wants those, that is a separate versioned change.
- **D-2.1 (kept original).** Multi-candidate per symbol is preserved end-to-end; the ranker receives one row per candidate. Rationale: two hypotheses are two decisions; collapsing them at the ranker hides the second option's rejection.
- **D-6.2 (kept original).** Hypothesis matching at T2 creates **exactly one** candidate per hit. Rationale: same-tick fan-out multiplies the D-14 log for no operator benefit; a second hypothesis surfaces via the next scanner tick or T5.
- **D-2.2 (revised).** Hypothesis enum is **renamed to side-agnostic kinds**. Original enum embedded side (long_continuation, short_failure); we replaced it. Rationale: the critique is correct — embedded side collapses the conditional-side-first principle.
- **D-5.1 (revised).** D-5 evaluates against **all sides in `conditional_side_map`** pre-trigger, resolved side post-trigger. Original ambiguously said "candidate side". Rationale: preserves I3.
- **D-1.1 / D-4.1 (revised).** D-1 and D-4 apply **only at T7**. Original said "any live state". Rationale: their inputs (expression, r_planned) don't exist until T7. §11.2 table pins applicability.

---

## 17. Open questions (deferred to owner)

- **Q1.** T5 resets `state_entered_at`, preserves `candidate_id`. Confirm.
- **Q2.** READY TTL 30 min vs "until compression relaxes" (T8 doing the work). Kept 30 min for now; alternate would drop T9-by-TTL.
- **Q4.** BLOCKED freezes TTL (D-10.3). Owner: confirm this reversal from the prior draft.
- **Q5.** Same-symbol collapse on Top 10 render — strictly downstream of ranker per §8.3.
- **Q6 (new).** `bias_hypothesis_reachability_matrix` (§7 item 3) — owner to sign off on the initial matrix before the pipeline goes live in shadow mode.
- **Q7 (new).** `evaluator_versions` file location and review cadence. Proposed: `research/pipeline_versions.json`, bumped per PR that touches an evaluator, reviewed weekly alongside D-14.