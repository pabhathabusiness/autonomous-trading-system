# TRADING PLAYBOOK v2.1.1 — owner-ratified rebuild framework, all decisions resolved

**Status**: DRAFT for review. **Not wired to production. No live trading
rules. No Top-10 / scanner / ranking / eligibility / Telegram changes.**

- `PLAYBOOK.md` (v1) — preserved unchanged.
- `PLAYBOOK_v2.md` — preserved unchanged.
- `PLAYBOOK_v2.1.md` — preserved unchanged.
- `PLAYBOOK_v2.1.1.md` — this document. Adds **D-11, D-12, D-13, D-14**
  owner decisions on top of v2.1. All decisions in D1–D14 are now
  ratified.

**Purpose**: complete the resolution of every unresolved decision left
open in v2.1. Everything else in v2.1 carries forward unchanged.

---

## How to read this document

Classifications are the same as v2 / v2.1:
**HARD SAFETY RULE (owner-selected)** · **EVIDENCE-BACKED CAUTION** ·
**RESEARCH HYPOTHESIS** · **RETIRED**. No composite score. No rule
voting. No automatic whitelist. Historical associations do not get
promoted to trading rules automatically.

---

## SECTION 0 — v2.1 → v2.1.1 diff

| Area | v2.1 | v2.1.1 |
|---|---|---|
| D-11 option-value model | Unresolved | **Ratified** — conservative ESTIMATED OPTION VALUE AT INVALIDATION model, current premium + delta (where available) + underlying-move-to-invalidation + conservative decay/IV adjustment. Never presented as exact. Missing/stale inputs → `OPTION RISK ESTIMATE = UNKNOWN` and trade does NOT auto-pass hard-risk check. See new § 18. |
| D-12 weekly PABS playbook refresh | Unresolved | **Ratified** — YES, but strictly scoped. Refresh may update diagnostics / sample counts / evidence tables / hypothesis status / flag stale rule assumptions. May NOT silently modify risk limits, rewrite hard rules, change scanner/ranking, or promote research to production. Any rule change requires explicit owner approval + versioned commit. See new § 19. |
| D-13 <2R handling | Unresolved | **Ratified** — during REBUILD PHASE, planned R < 2.0R is a **HARD BLOCK** unless the owner explicitly overrides. Override requires a logged reason. Cannot alter targets to manufacture 2R. Displays `POOR REWARD/RISK — BLOCKED`. Updates § 7 accordingly. |
| D-14 skipped-opportunity log | Unresolved | **Ratified** — structured log with 15 preregistered fields per skipped candidate; forward-outcome eval scheduled, not intraday. See new § 20. |
| § 7 R/reward | "normally pass" | **HARD BLOCK** under 2R during rebuild + override protocol |
| § 8 setup dimensions | unchanged | unchanged |
| § 14 trade card | HARD SAFETY block existed | **Added row**: D-13 R ≥ 2.0R OR override (with reason) |
| § 17 unresolved | 4 open (D-11 … D-14) | **0 open**. All D1–D14 ratified. New § 21 records rebuild-phase re-review triggers. |

Everything not listed above is inherited verbatim from v2.1.

---

## SECTION 1 — TRADING STYLE / SCOPE (unchanged from v2.1)

Two-layer decision model:

**Underlying setup layer** — direction, structure, support/demand,
resistance/supply, relative strength, SPY/sector context, technical
invalidation, technical target.

**Option expression layer** — call/put, strike, expiration, DTE,
moneyness, premium paid, estimated option loss at underlying
invalidation, contract count, planned account risk.

A valid underlying setup does NOT automatically mean the option
expression is acceptable. If the option cannot express the setup
within the account-risk budget → **SKIP THE TRADE**.

The playbook is primarily an **options-trading risk and execution
framework built on top of underlying technical analysis.**

---

## SECTION 2 — OWNER-RATIFIED SAFETY & PROCESS RULES (D1–D14)

The full ratified decision table now covers D1 through D14.

### D1 — Per-trade risk (HARD SAFETY RULE — inherited)
Normal ≈ 2% of equity; ceiling 3%; skip if smallest fit exceeds budget;
never tighten technical stop artificially.

### D2 — Daily-loss circuit breaker (HARD SAFETY RULE — inherited)
Stop after 2 full-risk losses OR ≈ 4% session drawdown; lockout for
rest of session.

### D3 — Concurrent positions (HARD SAFETY RULE — inherited)
Max 2 live option positions; max 1 per strongly-correlated
sector/theme; no force-close on rollover.

### D4 — Contract sizing (HARD SAFETY RULE — inherited)
1 contract default; 2 permitted iff combined planned loss ≤ 1R;
1 contract is not automatically acceptable — must still fit budget.

### D5 — Written thesis (HARD SAFETY RULE — inherited)
Mandatory pre-entry with 16 required fields. No thesis → no trade.

### D6 — First 15 minutes (HARD SAFETY RULE — inherited)
Read-only for 30 trading sessions; track skipped opportunities separately.

### D7 — Exit logic (HARD SAFETY RULE — inherited)
Retired fixed premium exits. New framework: underlying technical
invalidation + predefined technical target + account-risk backstop.

### D8 — Same-ticker re-entry (HARD SAFETY RULE — inherited)
No same-day re-entry after stop-out; next-session ok iff new setup;
wash-sale = tax concern, not signal.

### D9 — Review cadence (PROCESS — inherited)
Weekly review; playbook changes ≤ monthly unless safety defect.

### D10 — Caution delivery (PROCESS — inherited)
Dashboard shows all cautions; Telegram only material-context cautions.

### D11 — Option value at invalidation (HARD SAFETY RULE — NEW)

**Purpose**: derive `planned option loss $` from `underlying technical
invalidation` deterministically enough to fit the account-risk budget.

**Model** (conservative, MVP):

    ESTIMATED OPTION VALUE AT INVALIDATION =
        current_option_premium
        + delta × (invalidation_price − current_underlying_price)
        + conservative_decay_adjustment
        + conservative_iv_uncertainty_adjustment

where:

- `current_option_premium` — mid or last, at moment of thesis write-up.
- `delta` — from the option chain when available; treat as signed
  (positive for calls, negative for puts).
- `invalidation_price − current_underlying_price` — signed, straight
  from the underlying setup layer.
- `conservative_decay_adjustment` — for multi-day intent, subtract an
  owner-chosen theta-per-day × trading days to expected invalidation.
  Initial value: **0.5 × theta_per_day × days**, floored at zero. If
  theta is missing, use a conservative default of 5% of current
  premium per calendar day, capped at 30% of current premium total.
  This is a placeholder; do not treat as calibrated.
- `conservative_iv_uncertainty_adjustment` — subtract an additional
  10% of current premium to reflect the estimate can be worse than
  linear-delta suggests when volatility contracts on move-in-direction.
  Also a placeholder.

**Labeling** (mandatory):

- On every trade card the field is displayed as:
  `ESTIMATED OPTION VALUE AT INVALIDATION: $X.XX (estimate)`
- Never present the estimate as exact.
- The derived `planned option loss $` is labeled:
  `ESTIMATED PLANNED LOSS: $X (estimate; not a guarantee)`

**Missing-data policy**:

If ANY of the required inputs are missing, stale, or unreliable:

- `current_option_premium` unavailable → `OPTION RISK ESTIMATE = UNKNOWN`
- `delta` unavailable AND underlying is not deep ITM (|delta|→1.0 by
  approximation) → `OPTION RISK ESTIMATE = UNKNOWN`
- `underlying invalidation` not defined at entry → `OPTION RISK
  ESTIMATE = UNKNOWN`

When `OPTION RISK ESTIMATE = UNKNOWN`:

- The trade **does NOT auto-pass** the D1 per-trade risk check.
- Trade card renders `HARD SAFETY — D1 within budget: FAIL (estimate
  unknown)`.
- Owner may still take the trade only if they explicitly override
  (see D-13 override protocol; same shape) with a written override
  reason on the trade card.

**Do NOT build a full pricing engine yet.** The MVP above is the
initial implementation; a later Black-Scholes / IV-surface upgrade is
a separate, non-urgent research task.

### D12 — Weekly PABS playbook refresh (PROCESS — NEW)

**Ratified**: YES, weekly automation is allowed and expected.

**The weekly job MAY**:

- Refresh Schwab diagnostics (re-run `schwab_feedback`,
  `schwab_diagnostic`, `schwab_hypothesis_spy_load`,
  `schwab_mixed_correlation` against the newest CSV).
- Update sample counts in ticker-evidence tables (§ 13).
- Update evidence tables (marginal means, PF, WR by DTE / moneyness /
  regime).
- Update **hypothesis status** (H1..H7 in v2 § 9) — mark hypotheses
  as `SUPPORTED_ON_NEW_SAMPLE`, `STILL_INSUFFICIENT`, `WEAKENED`,
  `CONTRADICTED_ON_NEW_SAMPLE`.
- Flag rule assumptions that should be reviewed (e.g., "AAPL sample
  now n=87 vs n=61 in v2.1; label stable but confirm at next review").

**The weekly job MAY NOT**:

- Silently modify any owner risk limit (D1, D2, D3, D4).
- Automatically rewrite any HARD SAFETY RULE.
- Change scanner logic, ranking, or Top-10 selection.
- Promote a RESEARCH HYPOTHESIS into an EVIDENCE-BACKED CAUTION or a
  HARD SAFETY RULE.
- Add or remove tickers from any evidence-status label except through
  the recomputation of the labels' preregistered n / PF / WR
  thresholds (§ 13). The labels themselves change only through
  recomputation, not through discretion.

**Output**: a diff file `research/results/weekly_refresh_<YYYYMMDD>.md`
plus a **REVIEW-REQUIRED** section listing any material shifts (e.g.,
a ticker moved from SUPPORTED_SAMPLE to NEGATIVE_SAMPLE, or a
hypothesis flipped status).

**Approval**: any rule change proposal from this refresh requires
explicit owner approval AND a versioned commit (v2.1.2 or later)
before it takes effect on the trade card. The refresh CANNOT commit
to `PLAYBOOK_v*.md` on its own.

### D13 — <2R handling (HARD SAFETY RULE — NEW)

**During REBUILD PHASE**: planned reward/risk **< 2.0R** is a **HARD
BLOCK** on the trade card. The trade cannot be placed unless the owner
explicitly overrides.

**Override protocol**:

- The trade card exposes an `OWNER OVERRIDE` line requiring a written
  entry with these mandatory fields:
  1. Reason (why 2R minimum is being waived)
  2. Expected target (what the owner actually expects to achieve)
  3. Actual R multiple as measured against the technical target
     (e.g., `1.4R`)
  4. Why the trade is still being taken (setup quality, catalyst,
     conviction — free text)
- The trade card records the override on the paper-trade record so
  post-hoc review can measure whether overrides underperformed
  no-overrides.
- Overrides do NOT bypass D1 (risk budget), D3 (concurrent count),
  D4 (contract sizing), D5 (thesis), D7 (invalidation-based exit),
  or D11 (option-value estimate).

**Do NOT alter the technical target to manufacture 2R.** If the real
technical structure only supports 1.4R, the trade card renders:

    POOR REWARD/RISK — BLOCKED  (target 1.4R < 2.0R rebuild minimum)

and stops there unless the owner explicitly overrides via the protocol
above.

**Post-rebuild review**: after 30 trading sessions, the R-minimum can
be renegotiated. Until then, 2.0R is the hard floor.

### D14 — Skipped-opportunity log (PROCESS — NEW)

Every skipped candidate is logged with a **structured record**. The
purpose is to measure whether the rebuild-phase rules are protecting
capital or filtering too many valid setups.

**Storage**: append-only log at `research/results/skipped_opps.csv`
(or SQLite table; deferred to implementation). Fields:

- `timestamp` (ISO 8601 UTC)
- `ticker`
- `direction` (long | short)
- `setup_type` (from the setup dimensions catalog)
- `reason_skipped` (free text — one sentence)
- `spy_context` (BULLISH | MIXED | BEARISH | UNKNOWN)
- `sector_context` (active cluster labels or free text)
- `underlying_entry_level` (price)
- `technical_invalidation` (price)
- `technical_target` (price)
- `estimated_R` (target vs invalidation, at the option level)
- `dte` (integer, if considered an option trade)
- `moneyness` (ITM | ATM | OTM | N/A)
- `option_premium` (if available)
- `skip_source` (`HARD_SAFETY` | `CAUTION` | `OWNER_JUDGMENT`)

**Forward-outcome evaluation** (scheduled, NOT intraday):

Two weeks after each skip (or at expiration of the DTE, whichever is
sooner), a scheduled job appends to the skip record:

- `underlying_reached_1R` (bool)
- `underlying_reached_2R` (bool)
- `underlying_reached_3R` (bool)
- `underlying_hit_invalidation_first` (bool)

**Rules on how this log is used**:

- **Do NOT retune rules intraday** based on skipped-opportunity outcomes.
- Skipped-opportunity outcomes are read **only during scheduled research
  cycles** (D9 weekly review or the monthly playbook revision window).
- A pattern of "too many valid setups skipped by rule X" is a valid
  input to a proposed rule revision, but the revision itself follows
  the D12 approval path — no silent changes.

---

## SECTION 3 — RISK UNIT (R) (unchanged from v2.1)

> **R is based on account loss from the option position, while
> invalidation comes from the underlying setup.**

1R = the planned maximum account loss for this specific trade. Every
trade normalized so planned stop = −1R. Different trades can have
different 1R $ values.

---

## SECTION 4 — POSITION SIZING ORDER (unchanged from v2.1)

```
ACCOUNT SIZE
    ↓
ACCOUNT RISK BUDGET   (D1: 2% normal, 3% ceiling)
    ↓
UNDERLYING TECHNICAL INVALIDATION   (§ 1.1)
    ↓
ESTIMATED OPTION LOSS AT INVALIDATION   (D11 model)
    ↓
CONTRACT COUNT   (D4)
    ↓
EXPECTED R MULTIPLE   (must ≥ 2R per D13, else HARD BLOCK)
```

If invalidation exceeds budget → PASS.
If R < 2R → HARD BLOCK (D13).
If D11 estimate is UNKNOWN → HARD FAIL on D1 unless owner override
(D13-style override protocol).

---

## SECTION 5 — $1,000 WORKED EXAMPLE (unchanged from v2.1, D11-labels applied)

Account: $1,000. Normal risk $20. Contract $1.00. **Estimated** option
value at invalidation $0.80 (via D11 model). **Estimated** planned loss
$20. 1R = $20. Target option value $1.45 → +2.25R.

**Rows on the card that changed under v2.1.1**:

- `ESTIMATED OPTION VALUE AT INVALIDATION: $0.80 (estimate)`
- `ESTIMATED PLANNED LOSS: $20 (estimate; not a guarantee)`
- `Target R: +2.25R  (≥ 2.0R minimum per D13 — PASS)`

---

## SECTION 6 — ACCOUNT RISK LADDER (unchanged from v2.1)

Display aid. Percentage framework (D1) wins on conflict.

---

## SECTION 7 — R / REWARD STRUCTURE (updated by D13)

- Minimum planned reward ≥ **2R** — **HARD BLOCK** during rebuild if not met.
- 3R+ preferred when actual market structure provides room.
- Do NOT force every trade to exactly 2R.
- Do NOT widen the technical target to manufacture 2R.
- If real underlying structure supports < 2R: trade card renders
  `POOR REWARD/RISK — BLOCKED` and stops.

**Override**: available via D13 protocol. Override reason + expected
target + actual R + free-text justification recorded on the paper
trade.

---

## SECTIONS 8–12 (unchanged from v2.1)

- § 8 Setup dimensions rendered independently — no voting, no score.
- § 9 Market context: ALIGNED / MIXED / AGAINST / UNKNOWN; MIXED is
  CAUTION, not blocker.
- § 10 Option context always displayed; no automatic DTE ban; no
  automatic moneyness ban.
- § 11 Portfolio context always displayed; CORR_HIGH binary gate stays
  RETIRED.
- § 12 Historical risk pattern preserved: 13/15 for the true four-way
  intersection. Labeled ASSOCIATION, NOT PREDICTIVE RULE.

---

## SECTION 13 — TICKER EVIDENCE LABELS (unchanged from v2.1)

SUPPORTED_SAMPLE / PROVISIONAL / INSUFFICIENT_SAMPLE / NEGATIVE_SAMPLE
with the same n / PF / WR thresholds. Labels updated by the weekly
refresh (D12) via recomputation only.

---

## SECTION 14 — TRADE-CARD FORMAT (updated for v2.1.1)

New HARD SAFETY rows: **D-11 estimate available** and **D-13 R ≥ 2R**.

```
┌─────────────────────────────────────────────────────┐
│ TRADE IDEA                                          │
│   Ticker, Direction, Setup                          │
├─────────────────────────────────────────────────────┤
│ MARKET                                              │
│   SPY, Sector, RS                                   │
├─────────────────────────────────────────────────────┤
│ SETUP  (dimensions independently)                   │
│   Location, Structure, Compression, Momentum, Room  │
├─────────────────────────────────────────────────────┤
│ OPTION                                              │
│   DTE, Moneyness (signed %), Premium                │
│   Underlying invalidation:  $<price>                │
│   ESTIMATED OPTION VALUE AT INVALIDATION:           │
│     $<X.XX>  (estimate)                             │
│   ESTIMATED PLANNED LOSS:                           │
│     $<X>     (estimate; not a guarantee)            │
│   Planned loss % equity:  <X%>                      │
├─────────────────────────────────────────────────────┤
│ RISK                                                │
│   Account equity: $<X>                              │
│   1R:             $<X>  (= est planned loss)        │
│   Contract count: <N>   (D4 rule)                   │
│   Target R:       +<X.XX>R                          │
├─────────────────────────────────────────────────────┤
│ PORTFOLIO                                           │
│   Open positions, Premium exposure, Sector overlap, │
│   Correlated exposure                               │
├─────────────────────────────────────────────────────┤
│ CAUTIONS                                            │
│   • evidence-backed only — never blockers           │
├─────────────────────────────────────────────────────┤
│ HARD SAFETY                                         │
│   D1  Per-trade risk within budget:   PASS | FAIL   │
│   D3  Concurrent-position cap:        PASS | FAIL   │
│   D4  Combined loss ≤ 1R (if 2 ct):   PASS | FAIL   │
│   D5  Written thesis complete:        PASS | FAIL   │
│   D8  No same-day re-entry:           PASS | FAIL   │
│   D11 Option risk estimate available: PASS | FAIL   │
│   D13 Planned R ≥ 2.0R (or override): PASS | FAIL   │
│   §4  Sizing-flow discipline:         PASS | FAIL   │
├─────────────────────────────────────────────────────┤
│ OWNER OVERRIDE (used only when required)            │
│   For D13 (<2R):                                    │
│     Reason:                                         │
│     Expected target:                                │
│     Actual R multiple:                              │
│     Why still taking:                               │
│   For D11 (estimate UNKNOWN):                       │
│     (same 4 fields)                                 │
├─────────────────────────────────────────────────────┤
│ RESEARCH STATUS                                     │
│   Ticker evidence label, setup cell CI-low,         │
│   Prospective flags                                 │
└─────────────────────────────────────────────────────┘
```

Any HARD SAFETY FAIL without a corresponding override → card refuses
to advance.

---

## SECTION 15 — EXAMPLE OUTPUT (AAPL call, $1,000; updated with D11/D13)

```
TRADE IDEA
  Ticker: AAPL   Direction: Long call
  Setup:  inflection / near-demand + fresh MACD cross

MARKET
  SPY: MIXED
  Sector: no correlated tech-stack active
  RS: NEUTRAL

SETUP
  Location:       near demand (0.4 ATR from zone)
  Structure:      compression + break above 20-SMA
  Compression:    bb_state = COMPRESSION, squeeze_on = true
  Momentum:       macd_state = BULLISH_EXPANDING, bars_since_cross = 2
  Room to target: 2.3R to nearest supply

OPTION
  DTE:            14
  Moneyness:      ATM  (+0.4% from strike)
  Premium:        $1.00 ($100 total)
  Underlying invalidation:  $<inv>
  ESTIMATED OPTION VALUE AT INVALIDATION:
    $0.80 (estimate)
  ESTIMATED PLANNED LOSS:
    $20 (estimate; not a guarantee)
  Planned loss %:  1.9% of $1,000 equity  (< 2% normal)

RISK
  Account equity: $1,000
  1R:            $20
  Contract count: 1
  Target R:      +2.25R

PORTFOLIO
  Open positions: 1 (max 2 per D3)
  Premium exposure: $75 (7.5%)
  Sector overlap: 0
  Correlated exposure: none

CAUTIONS
  • MIXED market context — historical negative-mean bucket. Not a blocker.

HARD SAFETY
  D1  Per-trade risk within budget:      PASS   ($20 ≤ $20 normal)
  D3  Concurrent-position cap:           PASS   (1 → 2 after entry)
  D4  Combined loss ≤ 1R:                PASS   (1 contract, $20)
  D5  Written thesis complete:           PASS
  D8  No same-day re-entry:              PASS
  D11 Option risk estimate available:    PASS   (premium + delta + move + conservative adjustments)
  D13 Planned R ≥ 2.0R (or override):    PASS   (+2.25R ≥ 2.0R)
  §4  Sizing-flow discipline:            PASS

OWNER OVERRIDE: none required

RESEARCH STATUS
  Ticker evidence:   SUPPORTED_SAMPLE  (n=61, mean +$4.79, PF 1.39)
  Setup cell CI-low: no cell — detector 2 not yet run
  Prospective flags: H1 (same-day vs multi-day); intent = multi-day

STATUS: ALL HARD-SAFETY PASS — SETUP STILL REQUIRES OWNER DECISION
```

**Counter-example for D13**: same AAPL setup, but target only produces
+1.4R:

```
HARD SAFETY
  D13 Planned R ≥ 2.0R (or override):    FAIL   (1.4R < 2.0R rebuild min)

STATUS: POOR REWARD/RISK — BLOCKED

To override: fill in OWNER OVERRIDE (reason / expected target /
actual R / why still taking). Otherwise the card will not advance.
```

**Counter-example for D11**: same AAPL setup, but option delta
unavailable and underlying is ATM:

```
OPTION
  ESTIMATED OPTION VALUE AT INVALIDATION:  UNKNOWN
  OPTION RISK ESTIMATE = UNKNOWN

HARD SAFETY
  D11 Option risk estimate available:    FAIL   (delta missing; not deep ITM)
  D1  Per-trade risk within budget:      FAIL   (cannot verify — estimate unknown)

STATUS: INSUFFICIENT DATA — BLOCKED

To override: fill in OWNER OVERRIDE (reason / expected target /
actual R / why still taking). Otherwise the card will not advance.
```

---

## SECTION 16 — REBUILD PHASE (unchanged from v2.1)

Rules are temporary rebuild-phase owner constraints. Review after 30
trading sessions OR a materially larger new sample.

---

## SECTION 17 — DECISION STATE TABLE (D1 through D14, final)

| # | Decision | Status | Section |
|---|---|---|---|
| D1 | Per-trade risk cap | RATIFIED (2% normal / 3% ceiling) | § 2 D1 |
| D2 | Daily-loss circuit-breaker | RATIFIED (2 losses OR ≈4%) | § 2 D2 |
| D3 | Concurrent-position cap | RATIFIED (max 2; max 1 per correlated theme) | § 2 D3 |
| D4 | Contract sizing | RATIFIED (1 default; 2 iff combined ≤ 1R) | § 2 D4 |
| D5 | Written thesis pre-entry | RATIFIED (mandatory, 16 fields) | § 2 D5 |
| D6 | First-15-min read-only | RATIFIED (30 sessions; track skips) | § 2 D6 |
| D7 | Exit logic | RATIFIED (invalidation + target + risk backstop; fixed % RETIRED) | § 2 D7 |
| D8 | Same-ticker re-entry | RATIFIED (no same-day; next-session iff new setup) | § 2 D8 |
| D9 | Review cadence | RATIFIED (weekly review; monthly rule changes) | § 2 D9 |
| D10 | Caution delivery | RATIFIED (dashboard all; Telegram material only) | § 2 D10 |
| **D11** | **Option-value model** | **RATIFIED (conservative estimator; UNKNOWN blocks auto-pass)** | § 2 D11 + § 18 |
| **D12** | **Weekly PABS refresh** | **RATIFIED (YES with strict scope; owner approval to change rules)** | § 2 D12 + § 19 |
| **D13** | **<2R handling** | **RATIFIED (HARD BLOCK during rebuild; owner-override protocol)** | § 2 D13 + § 7 |
| **D14** | **Skipped-opportunity log** | **RATIFIED (structured 15-field log; scheduled forward-outcome eval)** | § 2 D14 + § 20 |

**Unresolved decisions in v2.1.1**: none.

**Next-window re-review triggers** (§ 21):
- 30 trading sessions elapsed → re-evaluate D6 (first-15-min), D13 (2R minimum)
- Meaningfully larger sample size on Schwab → re-evaluate D1/D2 percentages
- D14 skipped-opps log accumulates ≥ 30 records with outcomes → first
  formal review of whether rebuild rules are filtering too many valid
  setups

---

## SECTION 18 — OPTION-VALUE MODEL DETAIL (D11 implementation notes)

**Not yet implemented in production code.** This section is the spec.

Inputs required at entry:

- `underlying_price_at_entry` (float)
- `underlying_invalidation_price` (float)
- `option_side` ("C" or "P")
- `current_option_premium` (float, mid or last)
- `option_delta` (float; nullable)
- `option_theta` (float per day; nullable)
- `days_to_expected_invalidation` (float; nullable; owner-declared)

Output:

- `estimated_option_value_at_invalidation` (float or None)
- `option_risk_estimate` (str: "available" | "UNKNOWN")
- `estimated_planned_loss_dollar` (float or None)

Pseudocode (MVP):

```python
def estimate_option_value_at_invalidation(
    underlying_at_entry: float,
    invalidation_price: float,
    side: str,                       # "C" or "P"
    current_premium: float,
    delta: float | None,
    theta_per_day: float | None,
    days_to_invalidation: float | None,
) -> tuple[float | None, str]:
    if current_premium is None:
        return None, "UNKNOWN"
    if delta is None and side in ("C", "P"):
        # placeholder: unless deep-ITM by heuristic, refuse
        return None, "UNKNOWN"
    if invalidation_price is None or underlying_at_entry is None:
        return None, "UNKNOWN"

    move = invalidation_price - underlying_at_entry
    delta_effect = delta * move           # signed correctly for calls & puts
    est = current_premium + delta_effect

    # conservative decay
    if theta_per_day is not None and days_to_invalidation is not None:
        est -= 0.5 * abs(theta_per_day) * max(0.0, days_to_invalidation)
    elif days_to_invalidation is not None:
        # fallback: 5% of current premium per calendar day, cap 30%
        decay_cap = 0.30 * current_premium
        est -= min(0.05 * current_premium * max(0.0, days_to_invalidation), decay_cap)

    # conservative IV uncertainty
    est -= 0.10 * current_premium

    # floor at zero
    est = max(0.0, est)

    return est, "available"
```

**Every output must be rendered with the "(estimate)" tag.** This is
the initial concept, not a calibrated model. A later research task can
replace it with a full Black-Scholes / IV-surface pricer; that upgrade
is not required to ratify v2.1.1.

---

## SECTION 19 — WEEKLY REFRESH SCOPE (D12 implementation notes)

**Not yet implemented in production code.** Spec below.

**Scheduled**: Sunday evening (per D9). Job entry point:
`research/weekly_refresh.py` (deferred).

**Read**:
- Latest Schwab realized-gain/loss CSV export (owner drops in a known path).
- All `research/schwab_*.py` diagnostic modules.
- `PLAYBOOK_v2.1.1.md` version pin.

**Write** (allowed):
- `research/results/weekly_refresh_<YYYYMMDD>.md` — diff against last
  week's refresh.
- Updated evidence tables under `research/results/tables/`.
- Updated ticker-evidence labels (via preregistered recomputation
  only — see § 13).
- Updated hypothesis status entries.
- A `REVIEW-REQUIRED` block listing any material shift.

**MUST NOT write**:
- `src/**/*` (any production code)
- `config/**/*` (any live configuration)
- `PLAYBOOK*.md` (any playbook file)
- Any scanner / ranking / Top-10 / Telegram module

**Approval path for any rule change**:
1. Weekly refresh flags a proposed change in the REVIEW-REQUIRED block.
2. Owner reads, decides.
3. If accepted → owner (or a specifically-approved Claude session)
   authors `PLAYBOOK_v2.1.2.md` (or the next appropriate version) with
   the change explicit + versioned commit.
4. Only after commit does the trade card reflect the new rule.

---

## SECTION 20 — SKIPPED-OPPORTUNITY LOG (D14 implementation notes)

**Not yet implemented in production code.** Spec below.

**Storage**: `research/results/skipped_opps.csv` (append-only).

**Fields** (verbatim from D14):

```
timestamp
ticker
direction
setup_type
reason_skipped
spy_context
sector_context
underlying_entry_level
technical_invalidation
technical_target
estimated_R
dte
moneyness
option_premium
skip_source
```

**Skip sources** (enumerated):
- `HARD_SAFETY` — D1..D13 blocked
- `CAUTION` — evidence-backed caution, owner passed
- `OWNER_JUDGMENT` — owner chose to pass for a reason not on the card

**Forward-outcome fields** (populated by a separate job, not at skip
time):

```
underlying_reached_1R    (bool)
underlying_reached_2R    (bool)
underlying_reached_3R    (bool)
underlying_hit_invalidation_first  (bool)
first_check_date         (ISO 8601)
final_check_date         (ISO 8601)
```

**Update cadence**: forward outcomes are computed no more often than
weekly (aligned with D9). Do NOT recompute intraday.

**Analysis**: read only during D9 weekly review or the monthly rule-
revision window. A "too many valid setups filtered" pattern is input
to a proposed rule revision under the D12 approval path — not an
automatic rule change.

---

## SECTION 21 — REBUILD-PHASE RE-REVIEW TRIGGERS

Explicit gate criteria for when specific rules become eligible for
revision. Ratifying a change still requires the D12 approval path.

| Trigger | Rules eligible to revise |
|---|---|
| 30 trading sessions elapsed since v2.1 ratification | D6 (first-15-min), D13 (2R minimum) |
| Meaningfully larger Schwab sample (e.g., 6+ months post-v2.1.1) | D1 percentages, D2 daily-stop percentages |
| D14 log ≥ 30 skipped records with outcomes | Formal review of whether rebuild rules are filtering too many valid setups |
| Any HARD SAFETY defect observed live | Immediate review (bypasses monthly cadence in D9) |

---

## Version log

- **v2.1.1 (DRAFT) — 2026-09-16** — this document. Resolves D-11
  through D-14. All D1–D14 owner decisions ratified. Not yet ratified.
  Not wired.
- **v2.1 (DRAFT) — 2026-09-16** — see `PLAYBOOK_v2.1.md`. Preserved.
- **v2 (DRAFT) — 2026-09-16** — see `PLAYBOOK_v2.md`. Preserved.
- **v1 — 2026-09-16** — see `PLAYBOOK.md`. Preserved.

**No production changes.** No Top-10 / scanner / alerts / Telegram /
ranking / live-eligibility changes. STOP for owner review.
