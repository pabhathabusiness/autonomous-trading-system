# TRADING PLAYBOOK v2.1 — owner-ratified rebuild framework

**Status**: DRAFT for review. **Not wired to production. No live trading
rules. No Top-10 / scanner / ranking / eligibility changes.**

- `PLAYBOOK.md` (v1) — preserved unchanged.
- `PLAYBOOK_v2.md` — preserved unchanged.
- `PLAYBOOK_v2.1.md` — this document. Owner-ratified rebuild-phase
  constraints filled in on top of the v2 framework.

**Purpose**: turn the playbook into a *practical small-account operating
framework* that protects capital first, sizes trades from account risk
first, keeps setup dimensions separate, avoids overfit whitelist/blacklist
logic, treats historically-correlated loss conditions as CAUTIONS not
predictive rules, and defines R cleanly and consistently.

---

## How to read this document

- **HARD SAFETY RULE (owner-selected)** — capital or process constraint
  chosen by the account owner. Not historically optimized edge. Applies
  unconditionally in the rebuild phase.
- **EVIDENCE-BACKED CAUTION** — supported by the current 3-month sample.
  Historical association only. Not a predictive rule. Renders as a flag
  on the trade card; does not block.
- **RESEARCH HYPOTHESIS** — promising, needs prospective validation.
- **RETIRED** — contradicted or under-supported; kept in changelog only.

No composite score. No rule voting. No automatic whitelist. Historical
associations do not get promoted to trading rules automatically.

---

## Sources of evidence (unchanged from v2)

- `schwab_feedback.py` output — 1,311 realized lots, 872 grouped trades,
  Jun 16 → Sep 16 2026. Overall WR 27.2%, expectancy −$2.86/lot.
- `research/results/schwab_diagnostic_report.md`
- `research/results/schwab_hypothesis_spy_load_report.md`
- `research/results/schwab_mixed_correlation_report.md`

---

## SECTION 0 — v2 → v2.1 diff

| Area | v2 | v2.1 |
|---|---|---|
| Trading style / scope | Implicit | **Explicit two-layer framework** in § 1: underlying setup vs option expression. Options-first framing. |
| D1 per-trade risk | `OWNER DECISION REQUIRED` | **Ratified**: normal 2% of equity, ceiling 3%. Skip if smallest position can't fit. |
| D2 daily circuit-breaker | `OWNER DECISION REQUIRED` | **Ratified**: 2 full-risk losses OR ~4% session drawdown. Lockout: rest of session. |
| D3 concurrent positions | `OWNER DECISION REQUIRED` | **Ratified**: max 2 live option positions; max 1 per strongly-correlated sector/theme. No force-close if already above. |
| D4 contract sizing | `OWNER DECISION REQUIRED` | **Ratified**: 1 contract default; 2 permitted iff combined planned loss ≤ 1R. 1 contract is NOT automatically acceptable — trade still must fit risk budget. |
| D5 written thesis | `OWNER DECISION REQUIRED` | **Ratified**: mandatory; explicit required-fields list. No thesis → no trade. |
| D6 first 15 min | `OWNER DECISION REQUIRED` | **Ratified**: read-only for **30 trading sessions**; track skipped opportunities separately for later evaluation. |
| D7 exit logic | v1 fixed −35% / +50% / +100% remained as RESEARCH HYPOTHESIS | **Fully RETIRED as primary framework.** Replaced by: underlying technical invalidation + predefined technical target + account-risk backstop. |
| D8 same-ticker re-entry | v1 30-day rule was RESEARCH HYPOTHESIS | **Ratified**: no same-day re-entry after stopped-out loss; next-session ok iff genuinely new setup. 30-day tax wash-sale kept as accounting concern, NOT a trading rule. |
| D9 review cadence | `OWNER DECISION REQUIRED` | **Ratified**: weekly review; playbook changes ≤ monthly unless safety defect. |
| D10 caution delivery | `OWNER DECISION REQUIRED` | **Ratified**: dashboard shows all cautions; Telegram only sends material playbook-context cautions. No firehose. |
| R definition | Not defined | **New § 3**: 1R = planned max account loss for that specific trade. R normalized per-trade, not global. |
| Position sizing order | Not defined explicitly | **New § 4**: strict flow account → risk budget → invalidation → est option loss → contracts → R multiple. Never contracts-first. |
| $1,000 example | Absent | **New § 5**: concrete worked example with account = $1,000. Risk not hardcoded to option-price stop. |
| Risk ladder | Absent | **New § 6**: display-only equity-band ladder; percentage framework wins on conflict. |
| R/reward structure | Absent | **New § 7**: minimum 2R, 3R+ preferred; don't force, don't widen; POOR REWARD/RISK flag. |
| Ticker labels | EARNED / PROVISIONAL / UNPROVEN / CAUTION | **Renamed** to SUPPORTED_SAMPLE / PROVISIONAL / INSUFFICIENT_SAMPLE / NEGATIVE_SAMPLE (removes any "earned = permanent edge" connotation). |
| Trade-card format | Section had no RISK block | **Added RISK block** (account equity, 1R $, contract count, target R). |

---

## SECTION 1 — TRADING STYLE / SCOPE

The owner primarily trades **equity and ETF options**. PABS analyzes
the underlying stock/ETF and broader market context, but the actual
live expression is usually an options contract.

**Every trade decision must be evaluated on two separate layers:**

### 1.1 Underlying setup layer

- Direction
- Structure
- Support / demand
- Resistance / supply
- Relative strength
- SPY / sector context
- **Technical invalidation** (where the thesis is wrong on the underlying)
- **Technical target** (where the thesis is right on the underlying)

### 1.2 Option expression layer

- Call / put
- Strike
- Expiration
- DTE
- Moneyness
- Premium paid
- **Estimated option loss at underlying invalidation**
- Contract count
- **Planned account risk**

### 1.3 The two-layer rule (HARD SAFETY)

A valid underlying setup does **NOT** automatically mean the option
expression is acceptable.

If the option cannot express the underlying setup within the account-
risk budget → **SKIP THE TRADE**. Do not tighten the technical stop
artificially to make the option fit. Do not widen the technical target
artificially to make the R multiple fit. The underlying setup either
CAN be expressed within the risk budget, or it CANNOT — and if it
cannot, the trade is not taken.

**This playbook is therefore primarily an options-trading risk and
execution framework built on top of underlying technical analysis.**

---

## SECTION 2 — OWNER-RATIFIED SAFETY & PROCESS RULES (D1–D10)

Explicitly labeled: **OWNER-SELECTED SAFETY / PROCESS CONSTRAINTS.**
These are NOT historically optimized edge. They are the owner's
capital-protection and execution-discipline rebuild framework.

### D1 — Per-trade risk (HARD SAFETY RULE)

- **Normal planned risk**: ≈ **2% of current account equity**
- **Absolute ceiling**: **3% of current account equity**
- If the smallest practical position cannot fit inside the risk
  budget: **SKIP THE TRADE**
- Do **NOT** tighten the technical stop artificially just to make the
  trade fit

### D2 — Daily-loss circuit breaker (HARD SAFETY RULE)

- Stop trading after **whichever comes first**:
  - **2 full-risk losses** (i.e., 2 × 1R losses), OR
  - **≈ 4% account drawdown** in the session
- **Lockout**: rest of session (no more trades)

### D3 — Concurrent positions (HARD SAFETY RULE)

- **Rebuild-phase maximum**: **2 live option positions** at once
- **Max 1 position** from the same strongly-correlated sector/theme
- If already above the cap when v2.1 takes effect: **do not
  force-close** positions. Simply allow the book to naturally fall
  below the cap before opening another.

### D4 — Contract sizing (HARD SAFETY RULE)

- **Rebuild phase**: **1 contract** maximum by default
- However: 1 contract is **NOT automatically acceptable**. The trade
  must still satisfy the account-risk budget.
- **2 contracts permitted only if** combined planned loss ≤ 1R
- Example — if account-risk budget for the trade is $20:
  - ✅ 1 contract risking $20 total
  - ✅ 2 contracts risking $10 each ($20 combined)
  - ❌ 2 contracts risking $20 each ($40 combined)

### D5 — Written thesis (HARD SAFETY RULE)

Mandatory before every entry. Must include, at minimum:

- Ticker
- Direction
- Setup type
- Underlying entry trigger
- Technical invalidation (on the underlying)
- Technical target (on the underlying)
- Option expiration
- Strike
- DTE
- Moneyness
- Option premium
- Account risk ($)
- Expected R multiple
- SPY context
- Sector context
- Portfolio context

**No thesis → no trade.**

### D6 — First 15 minutes (HARD SAFETY RULE — TIME-LIMITED)

- **First 15 minutes of RTH session**: **READ-ONLY** during rebuild phase
- **Duration**: **30 trading sessions**
- **Track skipped opportunities separately** so this rule can later be
  evaluated on evidence rather than assumed correct forever.

### D7 — Exit logic (RETIRE fixed premium exits; new framework)

**RETIRED**:
- v1 fixed −35% premium stop
- v1 fixed +50% T1 exit
- v1 fixed +100% T2 exit

**Reason**: arbitrary fixed premium exits as a primary framework tie
your exit to a number that has no relationship to the underlying
setup. That is exit-by-percentage, not exit-by-thesis.

**New v2.1 exit framework** requires all three:

1. **Underlying technical invalidation** — where the setup is wrong
   on the stock/ETF chart. The stock/setup determines when the thesis
   is wrong. The option is only the vehicle.
2. **Predefined technical target** — where the setup is right.
   Specify at entry.
3. **Account-risk backstop** — if the option premium reaches or
   exceeds the planned account loss ($ = 1R for this trade), close.
   This is the hard floor even when the underlying has not touched
   invalidation yet.

Optional (owner discretion, not required):
- Partial off at intermediate R levels
- Time-stop (e.g., no progress in N sessions)

### D8 — Same-ticker re-entry (HARD SAFETY RULE)

- After a **stopped-out loss** on a ticker: **no same-day re-entry**
- **Next-session re-entry allowed only if** there is a genuinely new
  setup / thesis
- The old 30-day trading ban is **RETIRED as a market rule**
- Wash-sale treatment remains a **tax / accounting concern**, not a
  trading signal

### D9 — Review cadence (PROCESS)

- **Weekly review**: yes (run `schwab_feedback` + inspect the newest
  Schwab CSV export; compare to prior weeks)
- **Playbook changes**: no more frequently than **monthly**, unless
  a genuine safety defect is discovered
- Principle: **review often, retune rarely**

### D10 — Caution delivery (PROCESS)

- **Dashboard**: show all cautions for every trade card
- **Telegram**: only send cautions that **materially change decision
  context** for a specific proposed trade
- Do NOT create a noisy firehose

---

## SECTION 3 — RISK UNIT (R)

**R is based on account loss from the option position, while
invalidation comes from the underlying setup.** Keep these two layers
distinct at all times.

**Definition**:

> **1R = the planned maximum account loss for this specific trade.**

Every trade is normalized so **planned stop = −1R**. Upside is expressed
relative to that.

- Do NOT use a moving global meaning like "this trade risks −2R" unless
  it explicitly represents two separate risk units.
- **Preferred convention**: every individual trade's planned maximum
  loss is expressed as **−1R**.

**Examples**:

| Trade planned loss | Trade planned gain | R multiple |
|---|---|---|
| $20 | $40 | +2R |
| $20 | $60 | +3R |
| $20 | $100 | +5R |

**Different trades can have different 1R $ values.** If one trade risks
$40, then for THAT trade 1R = $40 — not 2R. This keeps expectancy math
clean across trades of different absolute size.

---

## SECTION 4 — POSITION SIZING ORDER (HARD SAFETY RULE)

Sizing logic **must always flow in this direction**:

```
    ACCOUNT SIZE
        ↓
    ACCOUNT RISK BUDGET     (2% normal, 3% ceiling — per D1)
        ↓
    UNDERLYING TECHNICAL INVALIDATION   (from the setup — per § 1.1)
        ↓
    ESTIMATED OPTION LOSS AT INVALIDATION   (option-value model)
        ↓
    CONTRACT COUNT
        ↓
    EXPECTED R MULTIPLE     (compared vs § 7 minimum)
```

**Never in reverse.**

Not allowed:

```
    I want 2 contracts
        ↓
    force the technical stop to fit
```

**If the technical invalidation requires more risk than the account
budget allows: PASS.**

Skipping is the correct action, not artificial stop-tightening.

---

## SECTION 5 — WORKED EXAMPLE: $1,000 ACCOUNT

*(Illustration only. Do NOT turn example values into production
defaults. Different setups will produce different numbers.)*

- Account equity: **$1,000**
- Normal planned risk (D1): **$20** (2%)
- Absolute ceiling (D1): **$30** (3%)

**Trade proposal**: 1 call contract at option premium $1.00 = $100
premium paid.

**Underlying setup provides a technical invalidation** at a specific
price level.

**Option-value model estimates** that if the underlying reaches that
invalidation price, the option would trade around $0.80.

- Planned loss = ($1.00 − $0.80) × 100 = **$20**
- Position size = **1 contract**
- Account risk = **$20** → fits inside the $20 normal budget ✅
- **1R = $20** for THIS trade

**Underlying setup target** produces an estimated option value of
$1.45 at target.

- Expected gain = ($1.45 − $1.00) × 100 = **$45**
- **Expected R multiple = $45 / $20 = +2.25R** ✅ (≥ 2R minimum per § 7)

**Important — what NOT to do**:

- ❌ Do NOT hardcode a "$0.20 option stop" universally. A $0.20 stop is:
  - 50% of a $0.40 option
  - 20% of a $1.00 option
  - 7% of a $3.00 option
  Same dollar → wildly different % risk. **Risk must be derived from
  account loss budget and technical invalidation, not from a
  premium-based rule of thumb.**

---

## SECTION 6 — ACCOUNT RISK LADDER (display aid, not a rule)

Owner-selected framework for the rebuild phase. **The percentage
framework in § 2/D1 remains the actual rule. This ladder is a display
aid.**

| Account equity | Typical planned risk / trade | Approximate daily stop |
|---|---|---|
| $750 – $1,249 | $15 – $20 | $30 – $40 |
| $1,250 – $1,999 | $20 – $30 | $40 – $60 |
| $2,000 – $2,999 | $30 – $40 | $60 – $80 |
| $3,000 – $4,999 | $40 – $60 | $80 – $120 |
| $5,000 + | Transition to percentage framework | Review |

**Actual rule** (from D1 + D2):
- Normal risk ≈ **2% of equity**
- Absolute ceiling = **3% of equity**
- Daily stop ≈ **4% of equity** OR **2 full-risk losses**, whichever first

**If the ladder disagrees with the percentage calculation, the
percentage framework wins.**

---

## SECTION 7 — R / REWARD STRUCTURE

**Preferred opportunity profile**:

- **Minimum planned reward ≥ 2R**
- **3R+ preferred** when the actual market structure provides room

**Do NOT** mechanically force every trade to exactly 2R. A setup can
be 2.1R, 2.7R, 3.4R, 5R — whatever the actual technical target and
invalidation produce.

**Do NOT** widen the target artificially to manufacture a better R:R.

If the real underlying structure does not provide at least 2R at the
option-level expression, mark the trade card:

> **POOR REWARD / RISK**

and **normally pass during rebuild phase**.

---

## SECTION 8 — SETUP DIMENSIONS (independent — no voting, no score)

Preserved from v2. Displayed side by side. **Never summed. Never
voted. No composite score.**

| Dimension | Field(s) / source |
|---|---|
| SPY context | `market.spy_regime_semantic` |
| Sector context | active correlation clusters in the open portfolio |
| Relative strength | `relative_strength.rs_class` |
| Trend / extension | `trend.stock_distance_to_sma50_atr` |
| Supply / demand | `supply_demand.nearest_demand_distance_atr`, `room_to_supply_R` |
| Compression | `compression_volatility.bb_state`, `.squeeze_on` |
| MACD / momentum | `momentum.macd_state`, `.bars_since_macd_cross` |
| Room to target | `supply_demand.room_to_supply_R` (also feeds § 7 minimum) |
| Historical setup evidence | bootstrap CI-low from `research/results/<detector>_*/stats.md` |

**Rule**: v2.1 does not require any number of these to be true. They
are visible on every trade card so the owner can decide.

---

## SECTION 9 — MARKET CONTEXT

Preserved from v2.

- **ALIGNED / MIXED / AGAINST / UNKNOWN** — same classification.
- **MIXED = EVIDENCE-BACKED CAUTION**, NOT an automatic no-trade.
- **RETIRED**: "AGAINST SPY is the main loss driver". Current evidence
  contradicted that (AGAINST was 5% of trades and profitable on
  average in the sample).

---

## SECTION 10 — OPTION EXPRESSION CONTEXT

Always display on every trade card:

- **DTE**
- **Moneyness %** (signed distance strike-vs-spot)
- **ITM / ATM / OTM** bucket
- **Premium**
- **Planned loss $** (= account risk = 1R for this trade)
- **Planned loss % of account**
- **Expected R multiple**
- **Same-day vs multi-day intent** (owner-declared at open)

**Rules for options context**:

- Do NOT create an automatic DTE ban.
- Do NOT create an automatic moneyness ban.
- Short-DTE and ATM/OTM are treated as **historical cautions** where
  appropriate — they appear as flags on the trade card, not as blockers.

---

## SECTION 11 — PORTFOLIO CONTEXT

Always display where available:

- Number of open option positions
- Total premium exposure ($)
- Premium exposure as % of account equity
- Same-sector exposure count
- Same-direction exposure count
- Index overlap count
- Correlation cluster labels
- Effective independent bet estimate (from cluster grouping)

**RETIRED**: the old `CORR_HIGH` binary flag as a hard gate.

Reason: it fired on effectively the entire historical option book
(817/817 in the sample) and has poor discriminatory value at this
book's operating pace.

Rendering is diagnostic; the boolean does not gate trades.

---

## SECTION 12 — HISTORICAL RISK PATTERN

**HISTORICAL ASSOCIATION — NOT A PREDICTIVE RULE.**

From the top-15 largest realized option losses in the 3-month sample
(`mixed_correlation_report.md`, § LARGEST-LOSSES OVERLAP):

| Condition at entry | Count / 15 |
|---|---:|
| MIXED SPY regime | 15 / 15 |
| Correlated cluster active | 15 / 15 |
| Short DTE (0-7) | 14 / 15 |
| ATM or OTM (not ITM) | 14 / 15 |
| MIXED + Correlated + Short DTE | 14 / 15 |
| **All four conditions coincident** | **13 / 15** |

Do NOT write "15/15" for the **four-way** intersection. The **four-way**
is 13/15.

**Reading**: label these four conditions on the trade card when they
coincide. Not a block.

---

## SECTION 13 — TICKER EVIDENCE LABELS

**Renamed from v2** — no "whitelist / blacklist / earned" language.

- **SUPPORTED_SAMPLE** — n ≥ 30 AND net P&L positive AND profit factor > 1.10
- **PROVISIONAL** — n ≥ 15, signal in either direction, insufficient
  sample to earn or exclude
- **INSUFFICIENT_SAMPLE** — n < 15. Evidence too thin to say anything
- **NEGATIVE_SAMPLE** — n ≥ 15 AND clearly negative (mean and PF both
  bad)

**Do NOT imply ticker-level profitability is permanent edge.** Labels
are display; they do not gate.

Current sample labels (subject to change every weekly review):

| Ticker | n | Label |
|---|---:|---|
| SPY | 134 | NEGATIVE_SAMPLE |
| NVDA | 62 | NEGATIVE_SAMPLE (borderline) |
| AAPL | 61 | **SUPPORTED_SAMPLE** |
| INTC | 35 | PROVISIONAL |
| RKLB | 25 | PROVISIONAL |
| TE | 23 | NEGATIVE_SAMPLE |
| SOFI | 19 | NEGATIVE_SAMPLE |
| QQQ | 15 | PROVISIONAL |
| everything else | < 15 | INSUFFICIENT_SAMPLE |

**Do NOT treat SUPPORTED_SAMPLE as permission to trade. It's a display
tag on top of the setup + option-expression + risk-budget checks.**

---

## SECTION 14 — TRADE CARD FORMAT (for eventual PABS rendering; not wired)

```
┌─────────────────────────────────────────────────────┐
│ TRADE IDEA                                          │
│   Ticker:      <TICKER>                             │
│   Direction:   <long call | long put>               │
│   Setup:       <detector / archetype>               │
├─────────────────────────────────────────────────────┤
│ MARKET                                              │
│   SPY context:      <ALIGNED|MIXED|AGAINST>         │
│   Sector context:   <active cluster labels>         │
│   Relative strength: <OUTPERFORMING|NEUTRAL|UNDER>  │
├─────────────────────────────────────────────────────┤
│ SETUP  (dimensions displayed independently)         │
│   Location:      <near_demand | mid | extended>     │
│   Structure:     <breakout | compression | drift>   │
│   Compression:   <bb_state, squeeze_on>             │
│   Momentum:      <macd_state, bars_since_cross>     │
│   Room to target: <room_to_supply_R>                │
├─────────────────────────────────────────────────────┤
│ OPTION                                              │
│   DTE:           <N days>                           │
│   Moneyness:     <ITM|ATM|OTM>  <signed pct>        │
│   Premium:       $<X>  ($<X>/contract)              │
│   Planned stop:  underlying at <price>              │
│   Planned loss $: $<X>                              │
│   Planned loss % equity: <X%>                       │
├─────────────────────────────────────────────────────┤
│ RISK                                                │
│   Account equity: $<X>                              │
│   1R:            $<X>  (= planned loss)             │
│   Contract count: <N>  (D4 rule)                    │
│   Target R:      +<X.XX>R                           │
├─────────────────────────────────────────────────────┤
│ PORTFOLIO                                           │
│   Open positions:    <N> (max 2 per D3)             │
│   Premium exposure:  $<X> (<X%> of equity)          │
│   Sector overlap:    <count same-sector-same-side>  │
│   Correlated exposure: <cluster labels>             │
├─────────────────────────────────────────────────────┤
│ CAUTIONS                                            │
│   (evidence-backed warnings only — never blockers)  │
│   • <one line per active caution>                   │
├─────────────────────────────────────────────────────┤
│ HARD SAFETY                                         │
│   (owner-approved constraints)                      │
│   D1 per-trade risk within budget:  PASS | FAIL     │
│   D3 concurrent-position cap:       PASS | FAIL     │
│   D4 combined-loss ≤ 1R (if 2 ct):  PASS | FAIL     │
│   D5 written thesis complete:       PASS | FAIL     │
│   D8 no same-day re-entry:          PASS | FAIL     │
│   § 4 sizing-flow discipline:       PASS | FAIL     │
├─────────────────────────────────────────────────────┤
│ RESEARCH STATUS                                     │
│   Ticker evidence:   <SUPPORTED_SAMPLE|...>         │
│   Setup cell CI-low: <value | "no cell">            │
│   Prospective flags: <research hypotheses tripped>  │
└─────────────────────────────────────────────────────┘
```

Any HARD SAFETY FAIL → the card refuses to advance. That's the
account-protection gate. **All other sections are display only.**

---

## SECTION 15 — EXAMPLE OUTPUT (AAPL call, $1,000 account)

*(Illustration. Do not turn example values into production defaults.)*

```
TRADE IDEA
  Ticker:     AAPL
  Direction:  Long call
  Setup:      inflection / near-demand + fresh MACD cross

MARKET
  SPY context:       MIXED
  Sector context:    no correlated tech-stack active
  Relative strength: NEUTRAL

SETUP
  Location:      near demand (0.4 ATR from nearest demand zone)
  Structure:     compression + break above 20-SMA
  Compression:   bb_state = COMPRESSION, squeeze_on = true
  Momentum:      macd_state = BULLISH_EXPANDING, bars_since_cross = 2
  Room to target: 2.3R to nearest supply

OPTION
  DTE:            14
  Moneyness:      ATM  (+0.4% from strike)
  Premium:        $1.00 ($100 total)
  Planned stop:   underlying below $<invalidation-level>
  Planned loss $: $19
  Planned loss %: 1.9% of $1,000 equity  (< 2% normal — ✅)

RISK
  Account equity: $1,000
  1R:            $19  (= planned option loss at underlying invalidation)
  Contract count: 1   (D4 default; combined loss $19 ≤ 1R ✅)
  Target R:      +2.37R   (option value at target ≈ $1.45)

PORTFOLIO
  Open positions:   1  (2 max per D3 — ✅ 1 slot remaining)
  Premium exposure: $75 (7.5% of equity)
  Sector overlap:   0 same-sector same-side
  Correlated exposure: none flagged

CAUTIONS
  • MIXED market context — historical negative-mean bucket in
    prior 3-month sample. Not a blocker.

HARD SAFETY
  D1 per-trade risk within budget:  PASS   ($19 ≤ $20 normal)
  D3 concurrent-position cap:       PASS   (1 → 2 after entry)
  D4 combined-loss ≤ 1R:            PASS   (1 contract, $19 loss)
  D5 written thesis complete:       PASS   (all fields present)
  D8 no same-day re-entry:          PASS   (no prior AAPL loss today)
  § 4 sizing-flow discipline:       PASS   (invalidation → loss → 1 ct)

RESEARCH STATUS
  Ticker evidence:   SUPPORTED_SAMPLE  (n=61, mean +$4.79, PF 1.39)
  Setup cell CI-low: no cell — detector 2 not run yet
  Prospective flags: H1 (same-day vs multi-day); intent = multi-day

STATUS: RISK FITS — SETUP STILL REQUIRES OWNER DECISION
```

---

## SECTION 16 — REBUILD PHASE

These rules are **temporary rebuild-phase owner constraints.**

**Review after**:

- **30 trading sessions**, OR
- A materially larger new sample (whichever comes first)

**Purpose**:

- Prevent catastrophic drawdown
- Reduce uncontrolled experimentation
- Improve trade-quality data (better inputs to the next diagnostic)
- Rebuild execution discipline

**Not the purpose**:

- Maximize short-term returns
- Prove the playbook right
- Replace judgment

---

## SECTION 17 — UNRESOLVED DECISIONS

Ratified in v2.1: D1–D10 (see § 2).

Still open:

- **D-11**: Option-value model choice for estimating "option loss at
  underlying invalidation". Options: pure delta approximation,
  delta+theta, full IV-based. Owner-selected. Recommend starting with
  delta approximation and reviewing after 30 sessions.
- **D-12**: Whether to run PABS setup detectors against the current
  weekly Schwab CSV automatically as part of the D9 weekly review, or
  keep it manual. Not required to trade.
- **D-13**: Whether to add a "poor-reward-risk" hard block during the
  rebuild phase, i.e. auto-skip when planned R < 2R at the option
  level. Currently § 7 says "normally pass during rebuild"; owner
  chooses whether that becomes a hard rule or stays discretionary.
- **D-14**: Format for the "skipped opportunities" log required by D6
  — how it's captured (notebook, CSV in the repo, dashboard entry).

---

## Version log

- **v2.1 (DRAFT) — 2026-09-16** — this document. Owner-ratified
  rebuild constraints D1–D10, R-unit definition, position-sizing
  order, $1,000 worked example, risk ladder, R/reward structure,
  ticker-evidence relabel, trade-card with RISK block, two-layer
  underlying/option framework. **Not yet ratified. Not wired.**
- **v2 (DRAFT) — 2026-09-16** — see `PLAYBOOK_v2.md`.
- **v1 — 2026-09-16** — see `PLAYBOOK.md`.

**No production changes.** No Top-10 / scanner / alerts / Telegram /
ranking / live-eligibility changes. STOP for owner review.
