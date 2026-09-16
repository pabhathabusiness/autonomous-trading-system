# TRADING PLAYBOOK v2 — capital-protection + decision-context framework

**Status**: DRAFT for review. **Not wired to production. No live trading
rules. No Top-10 / scanner / ranking changes.** See PLAYBOOK.md (v1)
for audit history — v1 is preserved unchanged.

**Purpose of v2**: transform the playbook from *"a list of hard rules
generated from one three-month sample"* into *"a capital-protection +
decision-context framework that distinguishes PROVEN safety rules from
PROVISIONAL research findings."*

---

## How to read this document

Every item carries one of four classifications:

- **HARD SAFETY RULE** — owner-approved capital protection or process
  constraint. Applies unconditionally. **Only the account owner can
  create or ratify these.** Where owner-approved values are missing,
  the placeholder reads `OWNER DECISION REQUIRED`.
- **EVIDENCE-BACKED CAUTION** — supported by the current 3-month sample
  but NOT proven causal. Historical association; treat as friction on
  the trade decision, not as a blocker.
- **RESEARCH HYPOTHESIS** — promising but requires prospective validation
  on a fresh sample. Do not act on it until it stabilizes.
- **RETIRED** — contradicted by the newer diagnostics or supported only
  by insufficient sample. Kept in the changelog for audit; not enforced.

**No composite score, no rule voting, no automatic ticker whitelist,
no permanent bans. Historical associations do NOT get promoted to
trading rules automatically.**

---

## Sources of evidence

- **`schwab_feedback.py` output** — 1,311 realized lots, 872 grouped
  trades, Jun 16 → Sep 16 2026. Overall win rate 27.2%, expectancy
  −$2.86/lot, cumulative account return −87.72% ($3,167 start +
  $2,035 contributions → $953 end).
- **`research/results/schwab_diagnostic_report.md`** — full diagnostic
  with moneyness (P1), DTE conditional on outcome (P2), intraday 100
  sample (P3), controlled SPY comparison (P4), revised labels (P5),
  separated inflection features (P6).
- **`research/results/schwab_hypothesis_spy_load_report.md`** — SPY
  alignment × portfolio load hypothesis (preregistered, verdict
  PARTIALLY SUPPORTED with important reframing).
- **`research/results/schwab_mixed_correlation_report.md`** — MIXED
  regime × correlated exposure × DTE × moneyness follow-up (3-of-3
  testable checks passed, C2 untestable because CORR_LOW empty).

---

## SECTION 0 — v1 → v2 change log

Every rule from v1 gets a disposition.

| v1 rule | v2 disposition | reason |
|---|---|---|
| **v1-1**: Max single-trade loss $50 | **HARD SAFETY RULE** — OWNER DECISION REQUIRED | Capital protection is owner-selected. v1 pulled 5%-of-current-equity from air; v2 does not invent the replacement. |
| **v1-2**: Max daily loss $150 | **HARD SAFETY RULE** — OWNER DECISION REQUIRED | Same rationale. |
| **v1-3**: Max 3 open option positions | **RETIRED** | Data shows 100% of option trades opened at 3+ positions. The threshold has never occurred in this book; the "cap" is not a cap. Reframed as a HYPOTHESIS in Section 6 (Portfolio Context). |
| **v1-4**: 1 contract per trade until account > $2,000 | **HARD SAFETY RULE** — OWNER DECISION REQUIRED | Contract sizing is owner-selected capital protection. |
| **v1-5**: NO 0DTE options | **EVIDENCE-BACKED CAUTION** | 340 lots, mean −$4.08 (0DTE bucket), −$730 total, WR 30%. Well-supported by sample but not a permanent ban. |
| **v1-6**: NO 1DTE options | **EVIDENCE-BACKED CAUTION** | 182 lots, mean −$10.08, worst DTE bucket. Well-supported but not permanent. |
| **v1-7**: NO SPY options | **EVIDENCE-BACKED CAUTION — REFRAMED** | SPY options were −$1,828 in the sample, BUT `hypothesis_spy_load` shows SPY concentration was in problematic combos (0-1 DTE, ATM/OTM, MIXED regime, high correlation). The problem isn't SPY-the-ticker; it's the specific DTE × moneyness × regime cell SPY was traded in. |
| **v1-8**: NO IWM options | **RETIRED** | n=2 is too small to declare a ticker-level rule. |
| **v1-9**: NO high-beta losers (ASTS, ACHR, OKLO, NOW, HPQ, QBTS, QUBT, KULR, TE) | **RETIRED** | Small samples across the list (mostly n=5-25). Not enough evidence for a permanent-ban list. See Section 4 for evidence-status treatment. |
| **v1-10**: Whitelist AAPL/PYPL/S/RPD/BUG/RKLB/IREN/QQQ | **RETIRED** | PYPL n=10, BUG n=9, RPD n=14, S n=12, IREN n=9 are all below any reasonable n=30 bar. Only AAPL (n=102) and RKLB (n=56) survive. Replaced by ticker-evidence-status in Section 4. |
| **v1-11**: NVDA on watch | **PROVISIONAL / CAUTION** | n=108, mean −$3.02, WR 29.6%. Genuinely neutral evidence — neither an edge nor a curse. |
| **v1-12**: Min 7 DTE, target 14-30 | **EVIDENCE-BACKED CAUTION on min-DTE; RETIRED on "target 14-30"** | The 14-30 DTE preference was inferred partly from n=5 in 31+ DTE — insufficient. The min-DTE side (avoid 0-1) is separately supported. |
| **v1-13**: No same-day close unless stop hit or +50% | **RESEARCH HYPOTHESIS** | Same-day mean −$4.45 vs multi-day mean −$3.19 in the grouped view; a small edge to holding. Intraday sample (P3) says session-favorable-option-lost = 38.1%. Enough to be a hypothesis, not enough to be a rule. |
| **v1-14**: Fixed exits at −35% / +50% / +100% / 5-day time-stop | **RESEARCH HYPOTHESIS — OWNER DECISION REQUIRED** | Percentages were not derived from data. If adopted, they are owner-selected. Playbook records them as candidate parameters, not established. |
| **v1-15**: No re-enter losing ticker within 30 days | **RESEARCH HYPOTHESIS** | 273 wash-sale lots ($5,298 disallowed) is a symptom; the rule that fixes it is behavioral, not automatic. Owner-selected cool-off periods are welcome; the specific 30-day IRS-driven number is a coincidence of the tax rule, not a trade-outcome finding. |
| **v1 setup context — 6-of-8 majority-vote checklist** | **RETIRED (voting)** — **PRESERVED (dimensions)** | The eight dimensions are useful to display. Summing them into "6 of 8 required" is a composite score by another name and was never validated. Section 5 renders them independently. |
| **v1 behavioral — thesis before entry, first-15-min no trade, stop after max-daily-loss, paper after 3 losing days, weekly review** | **HARD SAFETY RULE — OWNER DECISION REQUIRED per line** | Process constraints only the owner can commit to. v2 leaves them as candidate rules pending owner ratification. |

---

## SECTION 1 — HARD SAFETY RULES (capital protection)

**These are the only lines that block trades. Every unchecked item
below is `OWNER DECISION REQUIRED`.** v2 does not invent numbers to
replace v1's arbitrary $50 / $150; the owner picks them, or they
remain undecided and the rule stays inactive.

### 1.1 Per-trade risk cap

- [ ] **Max dollar loss per single option trade**: **`OWNER DECISION REQUIRED`**
  - Data-derived observations (not a rule):
    - Current account equity was ~$953 at the end of the analysis window
    - Largest single lot loss in the sample was $170 (~18% of that equity)
    - Multiple −$100 to −$170 single-lot losses concentrated in SPY options
  - The owner should state a per-trade dollar cap in absolute dollars
    OR a % of current equity, plus how it re-computes as equity moves.

### 1.2 Daily-loss circuit-breaker

- [ ] **Max total daily loss before session stop**: **`OWNER DECISION REQUIRED`**
  - Data-derived observations:
    - Longest losing-day streak in the sample was 9 consecutive close-days
    - Trades opened next day after a losing close-day averaged 10.9/day
      vs overall mean of 11.0/day — NO measurable revenge cadence at the
      day level
  - The owner should state a daily-loss dollar amount AND a lockout
    duration (e.g., "stop for the day", "paper-only for one day", etc.).

### 1.3 Concurrent-position cap

- [ ] **Max concurrent open option positions**: **`OWNER DECISION REQUIRED`**
  - Data-derived observations:
    - Median `open_position_count_at_new_trade_open` was 15+ in the sample
    - Max was 40 on the busiest days
    - v1's "max 3 concurrent" has never occurred in this book
  - The owner should state a cap that is (a) meaningful, and (b)
    reachable via a specific transition plan. See open owner decision D-1
    below.

### 1.4 Sizing (contracts per trade)

- [ ] **Contracts per option trade**: **`OWNER DECISION REQUIRED`**
  - Data-derived observations:
    - 42% of option lots were 1 contract; 32% were 2+ contracts.
    - Multi-contract mean −$5.24 vs 1-contract mean −$3.17. Small effect.
  - Owner-selected.

### 1.5 Written thesis before every entry

- [ ] **Adopt as HARD RULE?**: **`OWNER DECISION REQUIRED`**
  - Content specification: ticker, direction, expiry, strike, entry
    premium, stop (if any), target (if any), time-stop (if any),
    checklist of setup dimensions (Section 5), PABS output attached.
  - Behavioral rationale, not evidence-based on this sample.

### 1.6 First 15 minutes of session — no trades

- [ ] **Adopt as HARD RULE?**: **`OWNER DECISION REQUIRED`**
  - Behavioral rule from v1; no direct data support in this sample
    (no intraday timestamps).

### 1.7 Post-max-daily-loss lockout

- [ ] **Duration and mode (paper only / no trades / next-day only)**:
      **`OWNER DECISION REQUIRED`**

### 1.8 3-consecutive-losing-days circuit

- [ ] **Trigger and duration**: **`OWNER DECISION REQUIRED`**

### 1.9 Weekly review cadence

- [ ] **Fixed weekly cadence for re-running `schwab_feedback` and
      revising this playbook**: **`OWNER DECISION REQUIRED`**
  - Recommended (not a rule): 30 minutes on Sunday.

---

## SECTION 2 — MARKET CONTEXT (evidence-backed)

### 2.1 SPY alignment classification (used for CAUTION, not blocker)

Every prospective option trade receives one of:

- **ALIGNED** — trade side matches SPY BULLISH (calls) or BEARISH (puts)
  under the preregistered classification.
- **AGAINST** — trade side conflicts with SPY BULLISH or BEARISH.
- **MIXED** — SPY does not qualify as either BULLISH or BEARISH.
- **UNKNOWN** — insufficient SPY history (won't happen in practice).

### 2.2 Historical association per class (do not read as rules)

| Class | n option trades | Mean P&L | PF | Notes |
|---|---:|---:|---:|---|
| ALIGNED | 281 | +$0.42 | 1.03 | Roughly break-even historically |
| **MIXED** | **493** | **−$7.46** | **0.56** | **Largest loss bucket in sample** |
| AGAINST | 43 | +$6.01 | 1.65 | Small sample; profitable in this window |

### 2.3 What v2 says about SPY context

- **EVIDENCE-BACKED CAUTION**: **`MIXED` regime is where the historical
  loss lives.** Treat MIXED as a signal to raise scrutiny — verify
  Section 3 (setup) and Section 4 (ticker evidence) more carefully. **Not
  an automatic no-trade.**
- **RETIRED**: The prior "AGAINST SPY = biggest loss driver" framing.
  In this sample, AGAINST was 5% of option trades and PROFITABLE.
- **HARD RULE STATUS**: none. SPY context is context, not a gate.

### 2.4 Sector context (evidence-backed CAUTION)

Historical observation from `mixed_correlation_report`:
- `SECTOR_CLUSTER_quantum` active at entry: n=68, mean −$16.81, PF 0.27
- `SECTOR_CLUSTER_space_aero` active at entry: n=67, mean −$14.49, PF 0.25
- `BEARISH_INDEX_STACK` (2+ index puts) active at entry: n=33, mean −$20.80, PF 0.18

**EVIDENCE-BACKED CAUTION**: adding a same-sector same-direction trade
to a portfolio that already contains 2+ of the above patterns is
historically correlated with worse per-trade P&L. **Not an automatic
blocker**; render as a caution on the trade card.

### 2.5 Relative strength (evidence-backed, weakest of the 4 features)

From `schwab_diagnostic_report` P6:
- RS on trade side TRUE (n=265): mean +$1.34, PF 1.10
- RS on trade side FALSE (n=351): mean −$7.25, PF 0.59

**EVIDENCE-BACKED CAUTION**: the ONE single-feature discriminator that
was positive-mean on this sample. Do not build a rule on it; render it
as a positive signal on the trade card.

---

## SECTION 3 — SETUP DIMENSIONS (rendered independently — NO voting, NO score)

For every proposed option trade, PABS should return the following
eight fields from `research/context.py:compute_context_at(...)` and
display them side by side. **Not summed. Not voted. No composite.**

| Dimension | Field(s) | Historical association from sample |
|---|---|---|
| SPY context | `market.spy_regime_semantic` | See Section 2 |
| Sector context | derived from open-portfolio cluster analysis | See Section 2.4 |
| Relative strength | `relative_strength.rs_class` | See Section 2.5 |
| Trend / extension | `trend.stock_distance_to_sma50_atr` | Chased names (> 3 ATR above SMA50) appear in biggest single-trade losses |
| Supply / demand | `supply_demand.nearest_demand_distance_atr`, `supply_demand.room_to_supply_R` | Historical association; not a threshold rule |
| Compression | `compression_volatility.bb_state`, `compression_volatility.squeeze_on` | Feature TRUE mean −$7.45 (n=228) vs FALSE −$1.26 (n=388). Compression by itself NOT positive on this sample. |
| Momentum | `momentum.macd_state`, `momentum.bars_since_macd_cross` | Fresh MACD cross feature was NOT differentiating on this sample. |
| Historical setup evidence | Bootstrap CI-low from `research/results/<detector>_*/stats.md` | If available; else "NO CELL EVIDENCE". |

**Rule about this section**: v2 does NOT require any number of these
to be TRUE. Their job is to be visible on every trade card, so the
owner can decide.

- **RETIRED**: v1's "6 of 8 must be clear before opening." That was a
  majority-vote composite score by another name.
- **HARD RULE STATUS**: none in this section.

---

## SECTION 4 — TICKER EVIDENCE STATUS (replaces whitelist / blacklist)

Every ticker traded in the sample gets one of four statuses. Do NOT
declare an edge from small N.

### 4.1 Status legend

- **EARNED**: n ≥ 30 AND net P&L positive AND profit factor > 1.10.
- **PROVISIONAL**: n ≥ 15 AND signal in either direction, insufficient
  sample to earn or exclude.
- **UNPROVEN**: n < 15. Evidence too thin to say anything.
- **CAUTION**: n ≥ 15 AND clearly negative (mean and PF both bad).

### 4.2 Ticker table from the 3-month sample (grouped-trade view)

| Ticker | n | Net P&L | Mean | WR | PF | Status |
|---|---:|---:|---:|---:|---:|---|
| SPY | 134 | −$1,828.11 | −$13.64 | 23.1% | 0.41 | **CAUTION** |
| NVDA | 62 | −$326.60 | −$5.27 | 35.5% | 0.70 | **CAUTION** |
| AAPL | 61 | +$292.40 | +$4.79 | 44.3% | 1.39 | **EARNED** |
| INTC | 35 | −$65 (approx) | (approx neutral) | — | ~1.0 | **PROVISIONAL** |
| RKLB | 25 | +$165.55 | +$6.62 | 44.0% | 1.85 | **PROVISIONAL** (⚠ approaching EARNED; n < 30) |
| TE | 23 | −$152.83 | −$6.64 | 0.0% | 0.00 | **CAUTION** |
| SOFI | 19 | −$152.74 | −$8.04 | 21.1% | 0.40 | **CAUTION** |
| QQQ | 15 | +$101.89 | +$6.79 | 33.3% | 1.42 | **PROVISIONAL** |
| ACHR | 14 | −$201.64 | −$14.40 | 7.1% | 0.06 | **PROVISIONAL** (⚠ approaching CAUTION) |
| ASTS | 13 | −$214.18 | −$16.48 | 23.1% | 0.23 | **PROVISIONAL** |
| NVTS | 12 | −$96.87 | −$8.07 | 16.7% | 0.30 | **UNPROVEN** |
| RPD | 11 | +$186.49 | +$16.95 | 54.5% | 4.29 | **UNPROVEN** (⚠ was v1 whitelist — n too low) |
| QBTS | 15 | −$195.84 | −$13.06 | 40.0% | 0.24 | **PROVISIONAL** |
| QUBT | 10 | −$143.89 | −$14.39 | 10.0% | 0.02 | **UNPROVEN** |
| S | 9 | +$206.13 | +$22.90 | 55.6% | 3.28 | **UNPROVEN** (⚠ was v1 whitelist — n too low) |
| BUG | 7 | +$267.11 | +$38.16 | 57.1% | 3.80 | **UNPROVEN** (⚠ was v1 whitelist — n too low) |
| PYPL | 7 | +$782.73 | +$111.82 | 57.1% | 9.30 | **UNPROVEN** (⚠ was v1 whitelist — n too low; single big win) |
| IREN | 4 | +$81.12 | +$20.28 | 75.0% | 4.99 | **UNPROVEN** (⚠ was v1 whitelist — n < 5) |
| All others | < 15 | — | — | — | — | **UNPROVEN** by default |

### 4.3 What v2 does with ticker status

- **EARNED tickers**: eligible for options at any DTE / structure that
  the setup dimensions (Section 3) support. Not automatic entry.
- **PROVISIONAL tickers**: eligible; render "PROVISIONAL — n=X" on the
  trade card.
- **UNPROVEN tickers**: eligible; render "UNPROVEN — n<15" on the trade
  card. Not a blocker.
- **CAUTION tickers**: eligible only if the setup dimensions materially
  differ from the historical setups on that ticker (owner judgment).
  Rendered "CAUTION — n=X, mean −$Y" on the trade card.
- **RETIRED**: v1 "whitelist" and "blacklist" primitives. Neither exists
  in v2.
- **HARD RULE STATUS**: none. All ticker labels are diagnostic display.

---

## SECTION 5 — OPTION EXPRESSION CONTEXT (evidence, no rules)

Every trade card must display:

- **DTE at open** (integer + bucket): 0-1, 2-7, 8-14, 15-30, 31+
- **Moneyness** (ITM / ATM / OTM + signed % from strike)
- **Premium at risk** ($ amount)
- **Same-day vs multi-day intent** (declared by owner at open)

### 5.1 Historical associations (labeled — not rules)

Grouped-trade means from the 3-month sample:

| DTE bucket | n | Mean | PF |
|---|---:|---:|---:|
| 0DTE | 179 | −$4.08 | 0.78 |
| 1DTE | 105 | −$10.08 | 0.44 |
| 2-3 | 116 | −$3.16 | 0.78 |
| 4-7 | 95 | −$4.10 | 0.73 |
| 8-14 | 122 | −$0.59 | 0.96 |
| 15-30 | 68 | −$2.22 | 0.84 |
| 31+ | 132 | −$4.08 | 0.69 |

| Moneyness | n | Mean | PF |
|---|---:|---:|---:|
| ITM_deep | 11 | +$11.65 | 2.08 |
| ITM | 38 | +$13.09 | 3.15 |
| ATM | 341 | −$5.51 | 0.68 |
| OTM | 104 | −$10.05 | 0.47 |
| OTM_deep | 122 | +$0.91 | 1.07 |

### 5.2 What v2 says about option structure

- **EVIDENCE-BACKED CAUTION**: **0-1 DTE at ATM/OTM has been the
  worst-performing cell of the option book in this sample.** Render as
  a caution when this combination is proposed.
- **EVIDENCE-BACKED CAUTION**: **ITM options were profitable on this
  sample.** Not a rule. Note it on the trade card when applicable.
- **RETIRED**: v1's "target 14-30 DTE" specific preference was inferred
  partly from n=5 (31+ DTE bucket). Not enough sample.
- **RETIRED**: v1's fixed exit percentages (−35% stop, +50% T1, +100% T2,
  5-day time-stop) were arbitrary. Kept as candidate parameters for
  owner ratification (`OWNER DECISION REQUIRED`).

---

## SECTION 6 — PORTFOLIO CONTEXT (evidence, no rules)

At every proposed trade, PABS should display:

- Open option position count
- Open contract count
- Total open premium ($)
- Premium as % of estimated account equity (labeled `approximate`)
- Number of same-sector positions already open (long-side and short-side)
- Number of same-direction positions already open
- Number of index-option positions already open
- Correlation cluster diagnostics (list of active clusters like
  `SECTOR_CLUSTER_semiconductors`, `BEARISH_INDEX_STACK`)

### 6.1 What v2 says about portfolio state

- **RETIRED (as binary gate)**: the `CORR_HIGH` flag defined in
  `mixed_correlation`. It fired on 100% of option trades in the sample
  and therefore cannot function as a per-trade gate on THIS trader's
  book. The underlying diagnostics remain useful as display; the
  boolean does not.
- **RESEARCH HYPOTHESIS**: whether reducing the open-position count
  from median-15+ down to a materially smaller number improves
  outcomes. **Not testable on this sample** because there are no
  low-load counter-examples in the data.
- **HARD RULE STATUS**: none. Section 1 lists the concurrent-position
  cap as an OWNER DECISION REQUIRED — only the owner can add it.

---

## SECTION 7 — HISTORICAL RISK PATTERN (labeled association)

**Historical association — NOT a predictive rule.**

From the top-15 largest realized option losses in the 3-month sample
(`mixed_correlation_report.md`, § LARGEST-LOSSES OVERLAP):

| Condition at entry | Count / 15 |
|---|---:|
| MIXED SPY regime | **15 / 15** |
| Correlated cluster active | **15 / 15** |
| Short DTE (0-7) | 14 / 15 |
| ATM or OTM (not ITM) | 14 / 15 |
| MIXED + Correlated + Short DTE | 14 / 15 |
| **All four conditions coincident** | **13 / 15** |

The four-way intersection (MIXED + correlated + short DTE + ATM/OTM)
appears at 13 of the 15 largest losses. Correcting v1: **this is 13/15
for the four-way intersection, not 15/15**. Sub-intersections show
higher (up to 15/15).

**Reading**: this is a historical association. Do NOT turn it into a
rule like "don't trade when all four conditions coincide." The four
conditions co-occurred across 13 of the 15 loss cases; they also
co-occur across many non-loss cases in the same book (denominators
are in the diagnostic report). A rule would need base-rate analysis
plus prospective validation.

- **CLASSIFICATION**: **EVIDENCE-BACKED CAUTION** — display the four
  conditions as flags on the trade card when they coincide. Not a
  block.
- **RETIRED**: any prior text implying 15/15 for the four-way
  intersection.

---

## SECTION 8 — TRADE-CARD OUTPUT FORMAT (for eventual PABS rendering)

For each prospective trade, PABS should be able to render this card.
**This section specifies the shape of the display — nothing about
this is wired yet.**

    ┌─────────────────────────────────────────────────────┐
    │ TRADE IDEA                                          │
    │   Ticker:      <TICKER>       Status: <EARNED|...>  │
    │   Direction:   <long call | long put>               │
    │   Setup:       <detector name / archetype>          │
    ├─────────────────────────────────────────────────────┤
    │ MARKET                                              │
    │   SPY context:      <ALIGNED|MIXED|AGAINST>         │
    │   Sector context:   <cluster status>                │
    │   RS vs SPY:        <OUTPERFORMING|NEUTRAL|UNDER>   │
    ├─────────────────────────────────────────────────────┤
    │ SETUP  (each dimension displayed independently)     │
    │   Location:       <near_demand | mid | extended>    │
    │   Structure:      <breakout | compression | drift>  │
    │   Compression:    <bb_state, squeeze_on>            │
    │   Momentum:       <macd_state, bars_since_cross>    │
    │   Room to target: <room_to_supply_R>                │
    ├─────────────────────────────────────────────────────┤
    │ OPTION                                              │
    │   DTE:        <N days>                              │
    │   Moneyness:  <ITM|ATM|OTM>  <signed pct%>          │
    │   Premium:    $<X> ($<X>/contract)                  │
    │   Intent:     <same-day | multi-day>                │
    ├─────────────────────────────────────────────────────┤
    │ PORTFOLIO                                           │
    │   Open positions:      <N>                          │
    │   Total premium open:  $<X>                         │
    │   Premium/equity %:    <X%>  (approximate)          │
    │   Sector overlap:      <count same-sector-same-side>│
    │   Correlated stacks:   <list of active cluster tags>│
    ├─────────────────────────────────────────────────────┤
    │ CAUTIONS (evidence-backed only — never blockers)    │
    │   • <one line per active caution>                   │
    ├─────────────────────────────────────────────────────┤
    │ HARD SAFETY (owner-approved constraints)            │
    │   • <one line per constraint, PASS / FAIL / N/A>    │
    │     (if none exist, this section reads:             │
    │      "no owner-approved hard rules configured")     │
    ├─────────────────────────────────────────────────────┤
    │ RESEARCH STATUS                                     │
    │   Ticker evidence:      <EARNED|PROVISIONAL|...>    │
    │   Setup cell CI-low:    <value or "no cell">        │
    │   Prospective flags:    <list of research hypotheses│
    │                          that would trigger>        │
    └─────────────────────────────────────────────────────┘

---

## SECTION 9 — RESEARCH HYPOTHESES (needing prospective validation)

Do NOT act on these until they stabilize across a fresh sample.

- **H1**: Same-day option trades tend to underperform overnight+ holds
  on the same setup. Historical support in `schwab_diagnostic_report`
  (same-day mean −$4.45 vs multi-day −$3.19); intraday sample (P3) shows
  B' = 38.1% (session-favorable, option lost). Needs second window.
- **H2**: Fixed exits at −35% stop / +50% T1 / +100% T2 / 5-day time-stop
  improve outcomes vs discretionary exits. **Currently untested — the
  Schwab CSV shows realized exits, not what was planned.** Owner-selected.
- **H3**: Cool-off period on losing tickers reduces the wash-sale rate
  and follow-on losses. 273 wash-sale lots in the sample are a symptom.
  Owner-selected duration.
- **H4**: RS-on-trade-side is a real single-feature signal. n=265,
  mean +$1.34. Needs prospective validation on ≥ 200 more trades.
- **H5**: The four-way intersection (MIXED regime + correlated cluster
  + short DTE + ATM/OTM) is a genuine risk cell, not a coincidence.
  Needs base-rate analysis over the whole book plus a second window.
- **H6**: Reducing concurrent open positions from median 15+ to a
  smaller target improves per-trade outcomes. **Untestable on this
  sample** because no low-load counter-examples exist. Requires a
  behavioral experiment.
- **H7**: A fixed setup checklist that RECOMMENDS (not requires) 6+
  of 8 dimensions to be clear correlates with better P&L. NOT a rule
  in v2; explicitly retired as a required threshold.

---

## SECTION 10 — UNRESOLVED OWNER DECISIONS

**None of the following are decided in v2. Each requires an explicit
owner choice before it becomes a HARD SAFETY RULE.**

- **D-1**: Per-trade dollar risk cap. Absolute or % of equity. See § 1.1.
- **D-2**: Daily-loss dollar circuit-breaker and lockout duration. § 1.2.
- **D-3**: Concurrent-position cap and a transition plan from the
  current median-15+ operating state to that cap (paper account,
  one-position-at-a-time cadence, close-before-open discipline, etc.).
  § 1.3.
- **D-4**: Contract sizing rule. § 1.4.
- **D-5**: Whether to adopt a mandatory written thesis pre-entry as a
  hard rule. § 1.5.
- **D-6**: Whether to adopt "no trades in first 15 minutes" as a hard
  rule. § 1.6.
- **D-7**: Whether to adopt fixed exit rules (H2 above) as an owner
  rule, and if so at what percentages. § 5.2 / H2.
- **D-8**: Whether to adopt a same-ticker cool-off (H3) as an owner
  rule, and if so at what duration.
- **D-9**: Weekly review cadence (§ 1.9).
- **D-10**: How the trade-card `CAUTIONS` section should be surfaced
  to the owner (dashboard? phone? Telegram? — separate from Section 8
  format).

---

## SECTION 11 — RETIRED RULES (kept in changelog for audit)

Explicit list of v1 items no longer in v2:

- v1-3 (max 3 concurrent) — not achievable at current book scale.
- v1-8 (NO IWM) — n=2 too small.
- v1-9 (high-beta losers ban list) — small-N per ticker.
- v1-10 (whitelist of 8 tickers) — replaced by ticker-evidence-status.
- v1-12b (target 14-30 DTE) — 31+ DTE inference from n=5.
- v1-14 (specific exit %s) — arbitrary; converted to research hypothesis.
- v1 setup checklist 6-of-8 voting — composite score by another name.
- Any "AGAINST SPY is the primary loss driver" framing — data
  contradicted this.
- Any "15/15 for the four-way intersection" phrasing — corrected to
  13/15 for the true four-way; sub-intersections are separately reported.

---

## SECTION 12 — WHAT v2 IS NOT

- Not a set of live trading rules.
- Not a ranking / Top-10 / scanner input.
- Not wired to production PABS.
- Not a promise about the next 3 months.
- Not a substitute for owner judgment on capital-protection rules.

---

## Version log

- **v2 (DRAFT) — 2026-09-16** — this document. Reclassifies every v1
  rule against `schwab_diagnostic_report.md`,
  `schwab_hypothesis_spy_load_report.md`, and
  `schwab_mixed_correlation_report.md`. Retires overfit primitives.
  Adds evidence-status ticker table, option-structure display,
  portfolio-state display, historical-risk-pattern label, trade-card
  spec. Marks owner-decision placeholders. **Not yet ratified. STOP
  for review before ratification or any wiring.**
- **v1 — 2026-09-16** — see `PLAYBOOK.md`. Preserved unchanged.
