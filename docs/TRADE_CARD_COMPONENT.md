# TRADE CARD COMPONENT — Specification

> **DRAFT — for owner review, not wired to production.** Design-only artifact
> for the option-expression rewrite branch. Merges cleanly once the live
> droplet checkout is synced back. Modifies nothing under `src/static/`.

**Component:** `TradeCard`
**Consumers:** Top 10 page (`docs/TOP10_UX_SPEC.md`), Watchlist detail,
Scanner rows, Idea inspector.
**Contract source:** `/api/market/intel` per-ticker payload
(`docs/MARKET_INTELLIGENCE_SCHEMA.md`).
**Playbook binding:** PLAYBOOK_v2.1.1.md rules D-1..D-14.
**Version:** 0.2.0 — revised for critique round 1.

The card is the **ideas band** surface of the two-layer decision model. It
renders the *underlying setup layer*; the *option-expression layer* is a
sibling that mounts under READY / TRIGGERED. The card is a **finite state
machine** whose visible state is a projection of the 14 owner-specified
fields. **Ranking is out of scope.**

---

## 1. Design invariants

**I-1. Current bias and setup hypothesis are independent.** `current_structure_bias`
describes the tape now; `setup_hypothesis` describes the thesis being tested.
They MAY disagree — NVDA in section 5 is the canonical divergence case. The
card MUST render both and MUST NOT collapse them into one directional badge,
**including on TRIGGERED cards** (rule R-TRG, section 4).

**I-2. Side is conditional until a trigger fires.** `conditional_trade_side`
= `{ long_trigger?, short_trigger?, resolved_side? }`. The card MUST NOT
display `LONG` or `SHORT` as a resolved side unless `resolved_side` is
populated by a fired trigger. Side is decided by *which* trigger fires.

**I-3. BLOCKED is a branch, not a terminal.** Reachable from any
non-terminal state via a playbook gate (D-3, D-4, D-6, D-8, D-13). Clears
when every `blocked_reasons` entry clears. Does not consume the idea.

**I-4. The card never mutates ranking.** Read model only.

**I-5. Staleness is a first-class state axis.** Every field carries a
`computed_at`. **Fabrication is prohibited** — a stale primitive degrades the
field, it does not invent a plausible value.

**I-6. Invalidation is load-bearing.** Absent invalidation forces BLOCKED
with `NO_INVALIDATION`. Encoded as JSON Schema conditional required in
section 11. A level on the underlying, never a P/L number.

---

## 2. Design intent — trader's-eye order

| Zone | Purpose | Fields | Role tag |
|------|---------|--------|----------|
| A. Header | Identity + state | ticker, state pill (#4), freshness dot (#14) | STATE |
| B. Context | What is true now | #1 bias, #8 MTF, #9 RS, #7 S/D, #13 ERN | CTX / GATE |
| C. Hypothesis | What we are testing | #2 setup, #3 side, #5 trigger, #6 invalidation | THESIS / SIDE / FIRE / GATE |
| D. Risk | What losing looks like | R (from #6 + option layer) | RISK |
| E. Meta | Signal hygiene | #10 SQZ, #11 EVT, #12 NXT, #14 FRESH | GATE / META |

No zone is collapsible. Width 320 px fixed; height content-sized (~460 px);
border-radius 10 px; 1 px outer border colored by state (dashed for
DETECTED/EXPIRED per section 9).

```
+--------------------------------------------+
| A  TICKR   [STATE PILL]      * 4m ago      |
+--------------------------------------------+
| B  bias     MTF     RS     S/D     ERN     |
+--------------------------------------------+
| C  SETUP HYPOTHESIS                        |
|    conditional side  (LONG-if / SHORT-if)  |
|    trigger                                 |
|    invalidation                            |
+--------------------------------------------+
| D  R IMPLICATION                           |
+--------------------------------------------+
| E  SQZ | EVT | NXT | FRESH                 |
+--------------------------------------------+
```

---

## 3. Canonical field table (all 14)

Role vocabulary: **CTX** (context), **THESIS** (setup), **SIDE**
(conditional side), **GATE** (READY/BLOCKED), **FIRE** (drives TRIGGERED),
**RISK**, **DECAY** (READY→FORMING), **META** (freshness/derived), **STATE**.

| # | Field | Zone | Role | Domain | Null policy | Staleness | Affects |
|---|-------|------|------|--------|-------------|-----------|---------|
| 1 | `current_structure_bias` | B | CTX | `BULL`\|`BEAR`\|`RANGE`\|`MIXED`\|`UNKNOWN` | non-null; `UNKNOWN` on abstain | 15 min RTH / 1 d EOD | Gates D-6 |
| 2 | `setup_hypothesis` | C | THESIS | `{ label≤64, direction: LONG\|SHORT\|EITHER, rationale≤280 }` | non-null when state ≥ FORMING | 1 trading day | Absence ⇒ DETECTED; >24h ⇒ EXPIRED |
| 3 | `conditional_trade_side` | C | SIDE | `{ long_trigger?, short_trigger?, resolved_side? }` | ≥1 leg | inherits | `resolved_side` set ⇒ TRIGGERED |
| 4 | `trigger_state` | A | STATE | `DETECTED`\|`FORMING`\|`READY`\|`TRIGGERED`\|`BLOCKED`\|`EXPIRED` | non-null | derived | THE FSM state |
| 5 | `trigger` | C | FIRE | `{ kind, expr, armed_at?, fired_at? }` | non-null when state ∈ {READY, TRIGGERED} | 5 min | `fired_at` ⇒ TRIGGERED |
| 6 | `invalidation` | C | GATE | `{ level, kind, distance_R }` | non-null when state ∈ {FORMING, READY, TRIGGERED} | 15 min | `distance_R < 2.0` ⇒ R_UNDER_MIN; break ⇒ INVALIDATION_HIT |
| 7 | `supply_demand` | B | CTX | array ≤6 `{ kind, low, high, strength, age_bars }` | may be empty | 1H | Weak zones raise READY confidence gate |
| 8 | `mtf_context` | B | GATE | `{ tf_1m, tf_5m, tf_1h, tf_1d } → UP\|DOWN\|FLAT\|NA` | non-null | 1m=2m, 5m=10m, 1h=90m, 1d=1d | 1H/1D opposed ⇒ MTF_CONFLICT (see DD-4) |
| 9 | `rs_vs_spy` | B | GATE | `{ score: -3..3, direction, window }` | non-null | 15 min | Wrong-way demotes READY→FORMING |
| 10 | `compression` | E | GATE | `{ bbw_percentile, squeeze_on, bars_in_squeeze }` | non-null | 15 min | `bbw_pct ≤ 0.15` is a READY precondition for breakouts |
| 11 | `momentum_event` | E | GATE | `{ kind: BREAKOUT\|GAP\|EARN_REACT\|NEWS\|NONE, magnitude, at }` | `NONE` permitted | 30 min | ≠ NONE can escalate FORMING→READY |
| 12 | `next_level` | E | GATE | `{ side, price, distance_pct, distance_R }` | non-null when state ∈ {READY, TRIGGERED} | 15 min | `distance_R < 1.0` ⇒ NO_HEADROOM |
| 13 | `earnings` | B | GATE | `{ next_report_at?, days_until?, blackout, last_reaction_pct? }` | non-null | 1 day | `blackout=true` ⇒ EARNINGS_BLACKOUT |
| 14 | `freshness` | A + E | META | `{ oldest_field, oldest_age_s, status: FRESH\|AGING\|STALE\|EXPIRED }` | non-null | derived | `STALE` demotes; `EXPIRED` forces BLOCKED then EXPIRED |

Field #14 appears in **both** zone A (dot) and zone E (labeled cell) — both
tagged META. The dot is a redundant glance-only affordance; the labeled
cell is the canonical text render.

**Aliases:**
```
BiasSig    := enum { UP, DOWN, FLAT, NA }
TriggerRef := { kind: PRICE|VOLUME|PATTERN|COMPOSITE, expr: str,
                armed_at?: iso8601, fired_at?: iso8601 }
```

---

## 4. Field-by-field rendering rules

### Context zone (B)

- **#1 BIAS (CTX)** — `BULL` / `BEAR` / `MIXED` / `RANGE` / `UNKNOWN` followed
  by classifier reason ≤3 words. Empty: `bias: n/a`. Stale >15 min RTH:
  prefix `~`, drop reason.
- **#8 MTF (GATE)** — four cells `1m / 5m / 1H / 1D`, each `+` / `-` / `·`.
  Stale timeframe renders `·` with `stale` tooltip.
- **#9 RS (GATE)** — signed integer z-score, clipped -3..+3, plus arrow. Stale
  SPY tick ⇒ `RS: n/a`.
- **#7 S/D (CTX)** — `S 412.4 / D 407.1`. Empty within 3% band: `S/D: no zones`.
  Profile >24h old: prefix `S/D~`.
- **#13 ERN (GATE)** — `ERN 6d`, `ERN -2d`, or `ERN blackout`. Older than 24h:
  `ERN ?`.

### Hypothesis zone (C) — load-bearing

Left rule in state color anchors the eye.

- **#2 SETUP (THESIS)** — one plain-English sentence ≤90 chars. Empty:
  `no setup logged`; state forced to DETECTED. Older than 24h: strike-through
  crossbar, card degrades toward EXPIRED. **Rule R-TRG:** on TRIGGERED cards
  the setup line is retained above the resolved side so bias/hypothesis stay
  visually distinct from the fired side (I-1 in TRIGGERED).
- **#3 SIDE (SIDE)** — `LONG if A  |  SHORT if B` where A, B are 1–4 word
  tags. **Single-leg canonical form:** `LONG if A  |  —` (literal dash,
  see DD-7). The card MUST NOT display `LONG` or `SHORT` alone while state ∈
  {DETECTED, FORMING, READY}. On TRIGGERED, collapses to `→ LONG (A fired)`
  in the state color; the un-fired leg renders in **muted foreground** with
  `.struck` line-through — no directional color (rule R-DISCARD, DD-6).
- **#5 TRIG (FIRE)** — the precise event (e.g. `close_5m > 415.20 + rel-vol
  ≥ 1.5`). Two lines allowed for two-branch side. Price reference >2% from
  spot: prepend `far ·`.
- **#6 INV (GATE)** — `invalid < 406.9 (2h close)` — price + timeframe
  qualifier. Absent while state ∈ {FORMING, READY, TRIGGERED}: BLOCKED with
  `NO_INVALIDATION`. Already-broken level: value prefixed `HIT ·`, card
  transitions to BLOCKED with `INVALIDATION_HIT`, then EXPIRED once
  acknowledged.

### Risk zone (D)

- **R implication (RISK)** — two rows: `R = $X planned` + `R:R to next-level
  = 1 : Y`. Empty when option layer absent: `R: pending option layer`.
  Underlying moved >0.5% since compute: prefix `~`.
  Playbook enforcement is split (DD-2):
  - `invalidation.distance_R < 2.0` ⇒ BLOCKED, `R_UNDER_MIN` (D-3).
  - `next_level.distance_R < 1.0` ⇒ BLOCKED, `NO_HEADROOM` (D-3 companion).

### Meta zone (E) — 11 px muted, four cells, all role-tagged

- **#10 SQZ (GATE)** — `SQZ on` / `SQZ off` / `SQZ tight`.
- **#11 EVT (GATE)** — `breakout`, `gap+`, `gap-`, `ern-drift`, `sweep`, `—`.
- **#12 NXT (GATE)** — `+1.4% / -0.9%` signed distance to next R/S.
- **#14 FRESH (META)** — age of newest primitive. Also rendered as dot in
  zone A: green <5m RTH, amber 5–30m, red >30m or outside RTH.

---

## 5. Current structure bias vs setup hypothesis

The owner insisted these be first-class **separate** fields.

| Field | Question | Timeframe | Author |
|-------|----------|-----------|--------|
| #1 Bias | What is the tape doing right now? | Classifier over last N sessions | Engine, deterministic |
| #2 Hypothesis | What are we testing on it? | Lifecycle of one idea | Engine proposes, human ratifies |

```
bias        : BULL | BEAR | RANGE | MIXED | UNKNOWN     -- observed
hypothesis  : { direction: LONG | SHORT | EITHER, ... } -- proposed test
invariant   : bias and hypothesis.direction are independent;
              no rule of the form (bias ⇒ hypothesis.direction) exists.
```

| bias | hypothesis | Example |
|------|------------|---------|
| BULL | SHORT | Failure-of-HH short: if breakout fails, ride the flush |
| BEAR | LONG | VWAP reclaim long: bears fail to press through YL |
| RANGE | EITHER | Range-edge fade; side resolves on which edge trades first |
| MIXED | EITHER | Almost always BLOCKED under D-6; paper-trade note only |
| BULL | LONG | Trend continuation — common case |

### Worked example — divergence (rendered as the NVDA FORMING card)

- **Ticker:** NVDA
- **Bias:** `BULL · above 20/50, +slope` (last 12 sessions closed above 20
  SMA which is above 50 SMA; 50 SMA slope positive)
- **Hypothesis:** `failed-breakout short at 148.5 into vwap reclaim below`
  (`direction: SHORT`)
- **Conditional side:**
  - `SHORT if 148.5 rejects on 5m + rel-vol ≥ 1.5`
  - `LONG  if 5m close > 149.2 + rel-vol ≥ 1.5` (tape-continuation branch)
- **State:** FORMING — invalidation only 1.6R away (< 2R threshold, cited as
  the unmet precondition in the missing-for-READY banner)
- **Invalidation:** `invalid > 149.6 (2h close)`

The tape is bullish (context); the idea is a counter-tape short on failure
with a LONG branch that continues the tape if failure does not happen. The
card never claims NVDA is bearish; it claims one specific short setup is
being watched. Collapsing these two fields into one direction is the failure
mode the −87.72% quarter exposed.

**Rendering rule:** bias in the small monospace context strip (non-directional
color); setup in the larger sentence-cased hypothesis block. They cannot
merge visually. If they disagree, do **not** warn — this is expected.

---

## 6. Two-layer options framework mapping

| Layer | Fields on this card | Rendered where |
|-------|---------------------|----------------|
| Underlying setup | 1, 2, 5, 6, 7, 8, 9, 10, 11, 12, 13 | Zones A–C, E |
| Option expression | 3 (via trigger), R value in D | Zone D top row |
| State / hygiene | 4, 14 | Zone A |

The card never displays a specific strike, DTE, or option leg. A scan can
propose an idea before an option expression exists — card renders at FORMING
with `R: pending option layer`. When the sibling `OptionExpression` mounts,
it pushes R value into zone D via a one-way data prop.

---

## 7. Conditional trade side — formal type

```
ConditionalSide := {
  long_trigger?:  TriggerRef,   # if fires ⇒ resolved_side = LONG
  short_trigger?: TriggerRef,   # if fires ⇒ resolved_side = SHORT
  resolved_side?: LONG | SHORT  # set exactly once by the first trigger that fires
}
invariant: (long_trigger != null) OR (short_trigger != null)
invariant: resolved_side set iff the corresponding trigger.fired_at != null
invariant: at most one trigger may fire per idea lifecycle
```

Rendering:
- Both legs, unresolved: `LONG if <expr>  |  SHORT if <expr>`.
- One leg only, unresolved: `<SIDE> if <expr>  |  —`.
- Resolved: resolved side in state color as primary; un-fired leg muted +
  struck-through (rule R-DISCARD, DD-6).

---

## 8. FSM — states and transitions

```
S := { DETECTED, FORMING, READY, TRIGGERED, BLOCKED, EXPIRED }
initial := DETECTED
```

- **DETECTED** — ticker/idea seed exists but `setup_hypothesis` and
  `conditional_trade_side` are not both non-null. Empty-card render.
- **FORMING** — thesis and side conditions exist; ≥1 READY precondition unmet.
- **READY** — all preconditions met; trigger armed.
- **TRIGGERED** — a trigger fired; `resolved_side` populated.
- **BLOCKED** — a playbook gate is active. `blocked_reasons` is an **array**
  (multiple can be simultaneously active — DD-3).
- **EXPIRED** — terminal. Stale beyond 2× and unrecovered, or post-
  INVALIDATION_HIT after acknowledgment, or retention window elapsed.

### 8.1 BLOCKED sub-reasons

`blocked_reasons: array<enum>`, non-empty when `trigger_state = BLOCKED`.

```
SPY_MIXED_REGIME     # D-6: SPY MIXED and ticker in SPY cluster (r≥0.6)
LOAD_CAP             # D-4: already >2 concurrent positions
R_UNDER_MIN          # D-3: invalidation.distance_R < 2.0  (SCOPED, DD-2)
NO_HEADROOM          # D-3 companion: next_level.distance_R < 1.0
CLUSTER_OVERLAP      # D-13: correlated position already open at r≥0.6
EARNINGS_BLACKOUT    # D-8: within earnings blackout window
INVALIDATION_HIT     # underlying broke invalidation.level after TRIGGERED
STALE_DATA           # freshness.status == EXPIRED
MTF_CONFLICT         # 1H or 1D opposes hypothesis (LONG/SHORT only, DD-4)
NO_INVALIDATION      # field #6 absent (I-6)
```

**Deterministic display order** (banners are stable):
`STALE_DATA, NO_INVALIDATION, INVALIDATION_HIT, SPY_MIXED_REGIME, LOAD_CAP,
CLUSTER_OVERLAP, R_UNDER_MIN, NO_HEADROOM, EARNINGS_BLACKOUT, MTF_CONFLICT`.

**MTF_CONFLICT and hypothesis.direction = EITHER (DD-4):** when direction is
EITHER, MTF_CONFLICT is *inapplicable*, not *satisfied* — the gate is
**skipped**. However, at least one of `tf_1h`, `tf_1d` must be non-`NA`; if
both are `NA`, promotion to READY is denied as an unmet precondition
(not MTF_CONFLICT — that enum only applies for LONG/SHORT hypotheses).

### 8.2 Transition table

| # | From | To | Trigger event | Preconditions (ANDed) |
|---|------|----|--------------|---------------|
| T0 | (init) | DETECTED | ranker emits ticker | — |
| T1 | DETECTED | FORMING | ranker attaches thesis | `setup_hypothesis` non-null AND ≥1 side leg |
| T2 | FORMING | READY | precondition tick | freshness ∈ {FRESH, AGING} AND `invalidation.distance_R ≥ 2.0` AND `next_level.distance_R ≥ 1.0` AND `earnings.blackout == false` AND ((direction ∈ {LONG,SHORT} AND 1H/1D not opposed) OR (direction == EITHER AND ≥1 of 1H/1D non-`NA`)) AND (`squeeze_on` OR `momentum_event ≠ NONE`) AND (direction == EITHER OR RS consistent) AND `trigger.armed_at` non-null |
| T3 | READY | TRIGGERED | trigger fires | `trigger.fired_at` non-null AND `resolved_side` populated AND no active BLOCKED preconditions |
| T4 | READY | FORMING | decay | any of: `freshness == STALE`; `squeeze_on` flips off with no momentum event; RS becomes NEUTRAL (LONG/SHORT only); arm window (5 min) expires without fire |
| T5 | {FORMING, READY} | BLOCKED | playbook gate | any `blocked_reasons` entry from 8.1 becomes true |
| T6 | BLOCKED | previous | gate clears | ALL `blocked_reasons` clear AND idea still produced by ranker; returns to FORMING unless T2 also holds ⇒ READY |
| T7 | TRIGGERED | BLOCKED | invalidation hit | underlying prints through `invalidation.level` wrong-way vs `resolved_side`; append `INVALIDATION_HIT` |
| T8 | any | (removed) | ranker drop | idea no longer produced; card removed. Lifecycle event, not state |
| T9 | any | EXPIRED | terminal degradation | `freshness == EXPIRED` AND BLOCKED > 15 min, OR `INVALIDATION_HIT` acknowledged, OR `setup_hypothesis` age > 24h |
| T10 | {DETECTED, FORMING, READY} | BLOCKED | earnings tick | `earnings.blackout == true`; append `EARNINGS_BLACKOUT` |

**Per-tick evaluation order:**
```
1. Recompute freshness (field 14).
2. Evaluate T5 / T7 / T10 gates — BLOCKED wins over promotion.
3. Evaluate T9 (EXPIRED); EXPIRED is terminal, stop.
4. If state == BLOCKED, evaluate T6.
5. Else evaluate T3, T2, T4, T1 in that order.
6. Emit new state; store state_entered_at.
```

Every transition writes a row to the card's history strip (not on the base
card; visible in the detail modal).

---

## 9. State color / border / glyph rules

| State | Border | Pill | Left rule | Glyph |
|-------|--------|------|-----------|-------|
| DETECTED | 1 px dashed, muted `#3a3d46` | muted | muted, dashed | `·` |
| FORMING | 1 px **solid**, amber `#e0a83a` | amber tint / amber | amber | `◐` |
| READY | 1 px solid, blue `#4a9eff` | blue tint / blue | blue | `◑` |
| TRIGGERED | 1 px solid, green `#3fb27f` | green tint / green | green | `●` |
| BLOCKED | 1 px solid, red `#e15a5a` | red tint / red | red | `⊘` |
| EXPIRED | 1 px dashed, muted `#3a3d46` | muted | muted, dashed | `◌` |

Solid for the four active-lifecycle states; dashed for the two pre/post
states. This resolves the v0.1.0 section-9-vs-section-12 disagreement (DD-1).

- Never rely on color alone — every state pill carries a distinctive glyph.
- Keyboard focus ring: 2 px outer offset `#7fa8ff`.
- **Rule R-DISCARD:** on TRIGGERED cards the discarded leg renders in muted
  foreground with `text-decoration: line-through`. No directional color
  (avoids the pink-strikethrough glance-confusion — critique html_issues #9).
- **STALE amber ring:** when `freshness == STALE` and card not yet BLOCKED,
  an inset 2 px amber ring surrounds the card
  (`box-shadow: inset 0 0 0 2px var(--amber)`).
- **`?` suffix:** when ≥3 fields are stale-or-absent, the state pill appends
  `?` (`FORMING?`, `READY?`) — visual hint the state is under-supported.

---

## 10. Staleness policy

Fabrication is prohibited. Degrade the field; do not invent a value.

**Per-field ladder:**
1. **Fresh** — value rendered normally.
2. **Stale but present** — `~` prefix; tooltip carries last-seen timestamp.
3. **Absent** — empty-state string in muted foreground.
4. **Load-bearing absent** — if #6 invalidation, card transitions to BLOCKED
   with `NO_INVALIDATION`.

**Card-level derivation:**
```
age_i        := now - field_i.computed_at
ratio_i      := age_i / threshold_i
worst        := max ratio_i
status       := FRESH   if worst <  0.75
              | AGING   if worst in [0.75, 1.0)
              | STALE   if worst in [1.0, 2.0)
              | EXPIRED if worst >= 2.0
oldest_field := argmax_i ratio_i
```

- `AGING` → subdued zone-A dot.
- `STALE` → amber ring (section 9); forces T4 if in READY.
- `EXPIRED` → BLOCKED with `STALE_DATA`; > 15 min BLOCKED ⇒ T9 to EXPIRED.
- ≥ 3 fields stale-or-absent ⇒ zone-A dot red AND state pill suffixed `?`.
- Underlying last tick > RTH staleness (2 min intraday / 24 h overnight):
  entire card at 70% opacity with a `held` banner across zone A.
- The card never auto-advances on stale data. State can only regress or hold.

Explicit fabrication prohibitions: bias not inferred from S/D on stale
inputs; RS renders `n/a` against stale SPY tick; invalidation never rounded
to a nice number to fill the field; trigger price >2% from spot renders
`far ·`; already-broken level renders `HIT ·` and drives the transition.

---

## 11. JSON schema fragment (API payload)

Uses `if/then` so the wire format enforces I-6 and field #12's conditional
non-null clause.

```json
{
  "$id": "TradeCard/v0.2.0",
  "type": "object",
  "required": [
    "idea_id", "symbol", "current_structure_bias",
    "conditional_trade_side", "trigger_state",
    "supply_demand", "mtf_context", "rs_vs_spy",
    "compression", "momentum_event", "earnings", "freshness",
    "state_entered_at"
  ],
  "properties": {
    "idea_id": { "type": "string", "format": "uuid" },
    "symbol":  { "type": "string", "minLength": 1, "maxLength": 8 },
    "current_structure_bias": {
      "type": "string", "enum": ["BULL","BEAR","RANGE","MIXED","UNKNOWN"]
    },
    "setup_hypothesis": {
      "type": "object", "required": ["label","direction","rationale"],
      "properties": {
        "label":     { "type": "string", "maxLength": 64 },
        "direction": { "type": "string", "enum": ["LONG","SHORT","EITHER"] },
        "rationale": { "type": "string", "maxLength": 280 }
      }
    },
    "conditional_trade_side": {
      "type": "object",
      "properties": {
        "long_trigger":  { "$ref": "#/$defs/TriggerRef" },
        "short_trigger": { "$ref": "#/$defs/TriggerRef" },
        "resolved_side": { "type": "string", "enum": ["LONG","SHORT"] }
      },
      "anyOf": [ { "required": ["long_trigger"] }, { "required": ["short_trigger"] } ]
    },
    "trigger_state": {
      "type": "string",
      "enum": ["DETECTED","FORMING","READY","TRIGGERED","BLOCKED","EXPIRED"]
    },
    "blocked_reasons": {
      "type": "array", "uniqueItems": true, "minItems": 1,
      "items": { "type": "string",
        "enum": ["SPY_MIXED_REGIME","LOAD_CAP","R_UNDER_MIN","NO_HEADROOM",
                 "CLUSTER_OVERLAP","EARNINGS_BLACKOUT","INVALIDATION_HIT",
                 "STALE_DATA","MTF_CONFLICT","NO_INVALIDATION"] }
    },
    "trigger":      { "$ref": "#/$defs/TriggerRef" },
    "invalidation": { "$ref": "#/$defs/Invalidation" },
    "next_level":   { "$ref": "#/$defs/NextLevel" },
    "supply_demand":  { "type": "array", "maxItems": 6, "items": { "$ref": "#/$defs/SDZone" } },
    "mtf_context":    { "$ref": "#/$defs/MTF" },
    "rs_vs_spy":      { "$ref": "#/$defs/RS" },
    "compression":    { "$ref": "#/$defs/Compression" },
    "momentum_event": { "$ref": "#/$defs/MomentumEvent" },
    "earnings":       { "$ref": "#/$defs/Earnings" },
    "freshness":      { "$ref": "#/$defs/Freshness" },
    "state_entered_at": { "type": "string", "format": "date-time" }
  },
  "allOf": [
    { "if":   { "properties": { "trigger_state": { "enum": ["FORMING","READY","TRIGGERED"] } } },
      "then": { "required": ["invalidation","setup_hypothesis"] } },
    { "if":   { "properties": { "trigger_state": { "enum": ["READY","TRIGGERED"] } } },
      "then": { "required": ["trigger","next_level"] } },
    { "if":   { "properties": { "trigger_state": { "const": "BLOCKED" } } },
      "then": { "required": ["blocked_reasons"] } }
  ],
  "$defs": {
    "BiasSig":    { "type": "string", "enum": ["UP","DOWN","FLAT","NA"] },
    "TriggerRef": { "type": "object", "required": ["kind","expr"],
      "properties": {
        "kind": { "enum": ["PRICE","VOLUME","PATTERN","COMPOSITE"] },
        "expr": { "type": "string", "maxLength": 200 },
        "armed_at": { "type": "string", "format": "date-time" },
        "fired_at": { "type": "string", "format": "date-time" } } },
    "Invalidation": { "type": "object", "required": ["level","kind","distance_R"],
      "properties": {
        "level": { "type": "number" },
        "kind":  { "enum": ["SWING_LOW","SWING_HIGH","VWAP","ATR_STOP","CUSTOM"] },
        "distance_R": { "type": "number" } } },
    "NextLevel": { "type": "object", "required": ["side","price","distance_pct","distance_R"],
      "properties": {
        "side": { "enum": ["ABOVE","BELOW"] }, "price": { "type": "number" },
        "distance_pct": { "type": "number" }, "distance_R": { "type": "number" } } },
    "SDZone": { "type": "object", "required": ["kind","low","high","strength","age_bars"],
      "properties": {
        "kind": { "enum": ["SUPPLY","DEMAND"] },
        "low": { "type": "number" }, "high": { "type": "number" },
        "strength": { "type": "number", "minimum": 0, "maximum": 1 },
        "age_bars": { "type": "integer", "minimum": 0 } } },
    "MTF": { "type": "object", "required": ["tf_1m","tf_5m","tf_1h","tf_1d"],
      "properties": {
        "tf_1m": { "$ref": "#/$defs/BiasSig" }, "tf_5m": { "$ref": "#/$defs/BiasSig" },
        "tf_1h": { "$ref": "#/$defs/BiasSig" }, "tf_1d": { "$ref": "#/$defs/BiasSig" } } },
    "RS": { "type": "object", "required": ["score","direction","window"],
      "properties": {
        "score": { "type": "number", "minimum": -3, "maximum": 3 },
        "direction": { "enum": ["STRONGER","WEAKER","NEUTRAL"] },
        "window": { "type": "integer", "minimum": 1 } } },
    "Compression": { "type": "object", "required": ["bbw_percentile","squeeze_on","bars_in_squeeze"],
      "properties": {
        "bbw_percentile": { "type": "number", "minimum": 0, "maximum": 1 },
        "squeeze_on": { "type": "boolean" },
        "bars_in_squeeze": { "type": "integer", "minimum": 0 } } },
    "MomentumEvent": { "type": "object", "required": ["kind","magnitude","at"],
      "properties": {
        "kind": { "enum": ["BREAKOUT","GAP","EARN_REACT","NEWS","NONE"] },
        "magnitude": { "type": "number" },
        "at": { "type": "string", "format": "date-time" } } },
    "Earnings": { "type": "object", "required": ["blackout"],
      "properties": {
        "next_report_at":    { "type": "string", "format": "date" },
        "days_until":        { "type": "integer" },
        "blackout":          { "type": "boolean" },
        "last_reaction_pct": { "type": "number" } } },
    "Freshness": { "type": "object", "required": ["oldest_field","oldest_age_s","status"],
      "properties": {
        "oldest_field": { "type": "string" },
        "oldest_age_s": { "type": "integer", "minimum": 0 },
        "status":       { "enum": ["FRESH","AGING","STALE","EXPIRED"] } } }
  }
}
```

---

## 12. Rendering states — required visual affordances

| State | Border | Header chip | Side rendering | Extras |
|-------|--------|-------------|----------------|--------|
| DETECTED | dashed, muted | `DETECTED ·` | `no side yet` | ticker-only body; every field empty-state |
| FORMING | solid, amber | `FORMING ◐` | conditional (both legs, or `— (leg absent)`) | missing-preconditions banner |
| READY | solid, blue | `READY ◑` | conditional (both legs) | armed indicator, arm-window countdown |
| TRIGGERED | solid, green | `TRIGGERED ●` | resolved primary + muted-struck un-fired leg (R-DISCARD) | fired-at timestamp, inv distance |
| BLOCKED | solid, red | `BLOCKED ⊘ · <reasons>` | conditional legs, dimmed | reasons banner (multi-reason) + clearance predicate |
| EXPIRED | dashed, muted | `EXPIRED ◌` | last-known side, muted | reason (`stale >2×`, `invalidation-hit`, `window closed`) |

All states MUST render all 14 fields. BLOCKED does not hide fields; it dims
them and pins the reasons to the top of zone E.

---

## 13. Empty / DETECTED card

A card with nothing but a ticker and a freshness reading is a valid render:
- Zone A: ticker, `DETECTED ·` pill, freshness dot.
- Zone B: every context field renders its empty-state string.
- Zone C: `no setup logged`, `side: unset`, `trigger: unset`,
  `invalidation: unset`.

An unripe idea should never look like it could be traded. DETECTED cards are
routinely present at open before the ranker attaches theses; they are not
errors.

---

## 14. Interaction

Base card is read-only. Click anywhere opens the detail modal (history strip,
option expression component, chart embed). Keyboard: `Enter` opens detail;
`i` toggles invalidation-only focus. No hover state changes rendered values —
hover reveals tooltips only.

---

## 15. Testability

Each transition is a unit-testable predicate. Every transition and every
`blocked_reasons` entry MUST have at least one test before wiring.

```python
def test_T2_ready_requires_2R_invalidation():
    c = card_with(state='FORMING', invalidation_distance_R=1.6, **ready_ok)
    assert step(c).trigger_state == 'BLOCKED'
    assert 'R_UNDER_MIN' in step(c).blocked_reasons

def test_no_headroom_distinct_from_r_under_min():
    c = card_with(state='READY',
                  invalidation_distance_R=2.5, next_level_distance_R=0.8)
    r = step(c).blocked_reasons
    assert 'NO_HEADROOM' in r and 'R_UNDER_MIN' not in r

def test_bias_hypothesis_independence_nvda():
    c = card_with(bias='BULL', hypothesis_direction='SHORT',
                  invalidation_distance_R=2.2, **ready_ok)
    assert step(c).trigger_state == 'READY'

def test_either_skips_mtf_conflict():
    c = card_with(hypothesis_direction='EITHER',
                  tf_1h='DOWN', tf_1d='UP', **ready_ok)
    assert 'MTF_CONFLICT' not in step(c).blocked_reasons

def test_multi_reason_blocked_display_order():
    c = card_with(spy_regime='MIXED', invalidation_distance_R=1.3,
                  in_spy_cluster=True)
    assert step(c).blocked_reasons == ['SPY_MIXED_REGIME', 'R_UNDER_MIN']

def test_triggered_preserves_bias_and_hypothesis():
    c = card_with(state='READY', bias='RANGE',
                  hypothesis_direction='EITHER', fires='LONG')
    r = step(c)
    assert r.trigger_state == 'TRIGGERED' and r.setup_hypothesis is not None
```

---

## 16. Non-goals / out of scope

- No ranking. No state authorship. No broker calls. No portfolio-level R
  budgeting beyond LOAD_CAP. **No modification** of `src/static/index.html`,
  `src/static/app.js`, or any existing frontend file — this ships as a
  standalone artifact for design review and merges via the option-expression
  rewrite branch once wiring is authorized.

---

## 17. Design decisions (responses to critique round 1)

**DD-1 · FSM extended to 6 states** — `{DETECTED, FORMING, READY, TRIGGERED,
BLOCKED, EXPIRED}`. Sections 8, 9, 12, 13, field-#4 domain, and the JSON
schema enum now all agree. DETECTED and EXPIRED had lifecycle meaning in
v0.1.0 (empty-card, decay paths); demoting them to sub-tags would have lost
information the owner asked for.

**DD-2 · R_UNDER_MIN split from NO_HEADROOM** — `R_UNDER_MIN` now means
exclusively `invalidation.distance_R < 2.0`. `NO_HEADROOM` captures
`next_level.distance_R < 1.0`. The META card cites `R_UNDER_MIN` against
invalidation (not R:R-to-next-level).

**DD-3 · `blocked_reasons` is an array** — wire type moved from single enum
to `array<enum>` with deterministic display order. META serializes two
simultaneous reasons cleanly.

**DD-4 · EITHER semantics for MTF** — `hypothesis.direction == EITHER`
**skips** MTF_CONFLICT rather than passing it. If both `tf_1h` and `tf_1d`
are `NA`, promotion is denied as an unmet precondition (not MTF_CONFLICT).
Closes the "EITHER as escape hatch" loophole.

**DD-5 · Rule R-TRG** — hypothesis stays visible on TRIGGERED cards. Setup
line is retained above the resolved side so I-1 survives into the fired
state. AMD card demonstrates.

**DD-6 · Rule R-DISCARD** — un-fired leg loses directional color on
TRIGGERED. Renders in muted foreground with line-through. Closes
`html_issues` #9 (pink strikethrough could read as live SHORT).

**DD-7 · Single-leg canonical form** — `LONG if <expr>  |  —` (literal dash).
NVDA and META now follow this. Prior `SHORT if — (leg absent)` form is gone.

**DD-8 · Role vocabulary** — added `RISK` and `STATE`. All four zone-E cells
carry role tags. Zone D's `RISK` tag is defined.

**DD-9 · NVDA is now the divergence exemplar** — FORMING card matches
section 5 (BULL bias, SHORT failed-breakout at 148.5). A separate FORMING
variant (T4-decay demo) demonstrates the tape-continuation LONG.

**DD-10 · Light-mode CSS** — added `@media (prefers-color-scheme: light)`
guarded by `:root:not([data-theme="dark"])`. Explicit `<body>` background in
both themes.

**DD-11 · FSM SVG completeness** — T5, T7, T9, T10 all carry visible labels.
A cross-reference table under the SVG double-encodes each Tn to its trigger
event.

**DD-12 · Demo cards added** — the HTML now renders 8 cards covering the 6
states plus 2 lifecycle-transition demos: DETECTED, FORMING(NVDA divergence),
FORMING(T4 decay with `~` prefix + amber ring), READY, TRIGGERED, BLOCKED
(two-reason banner), BLOCKED(T7 with `HIT ·` prefix), EXPIRED(with `held`
banner + 70% opacity).

**DD-13 · Kept from v0.1.0 despite critique.**

- *"Add a state color for hypothesis.direction = EITHER."* Rationale: EITHER
  is a property of the hypothesis, not a state. Adding a fifth branch color
  risks visually equating EITHER with a resolved side. R-TRG and R-DISCARD
  address the concrete post-fire confusion without introducing a new axis.

- *"Freshness zone-A dot needs a textual label."* Rationale: field #14 is
  redundantly text-rendered in zone E's `fresh` cell. The zone-A dot is a
  glance-only affordance; a hover tooltip carries the text. Adding a label
  duplicates the redundancy already present.

- *"Worked-example cards for every transition."* T4 and T7 are added; T5,
  T6, T8, T9, T10 are represented by state-terminal cards. Adding a card
  per transition balloons the review artifact without adding distinct
  visual grammar.
