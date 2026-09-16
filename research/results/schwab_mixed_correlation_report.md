# SCHWAB FOLLOW-UP — MIXED SPY REGIME × CORRELATED EXPOSURE × DTE × MONEYNESS

**Hypothesis under test**: losses are explained better by trading in unclear SPY regimes while stacking correlated short-duration option exposure, than by simple directional disagreement with SPY.

All thresholds preregistered in the module docstring (`research/schwab_mixed_correlation.py`) BEFORE inspecting any P&L. No tuning post-hoc.

**No production changes.** Diagnosis only.

## DATA COVERAGE

- Grouped trades: **872** (options: **817**).
- Option trades with underlying bars in cache: **616 / 817** (75.4%).
- Pairwise 200-bar Pearson r precomputed over 40 tickers → **780** pairs available.
- Alignment distribution: ALIGNED 281, AGAINST 43, MIXED 493, UNKNOWN 0.
- Trades classified CORRELATION_HIGH by the preregistered rule: **817 / 817** (100.0%).

## CORRELATION RULE — verbatim from preregistration

At each option trade's open, examine the currently-open positions BEFORE adding this new trade. CORRELATION_HIGH iff ANY of:
- **(a)** two or more open positions share the SAME sector AND the SAME option side (both C or both P);
- **(b)** an open broad_index option + a same-direction non-index option in {mega_tech, semiconductors};
- **(c)** two or more open positions with same side and pairwise 200-day Pearson r ≥ 0.6.

A trade opened into an empty portfolio (no prior open positions) is LOW by construction.

## ALIGNMENT × CORRELATION (2×2)

All option trades. Rows: SPY-alignment. Columns: correlation flag at open.

| Alignment | Correlation | n | win% | mean | median | PF | total |
|---|---|---:|---:|---:|---:|---:|---:|
| ALIGNED | LOW | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| ALIGNED | HIGH | 281 | 30.2% | $0.42 | $-8.32 | 1.03 | $116.63 |
| MIXED | LOW | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| MIXED | HIGH | 493 | 28.2% | $-7.46 | $-10.64 | 0.56 | $-3,679.67 |
| AGAINST | LOW | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| AGAINST | HIGH | 43 | 44.2% | $6.01 | $-6.32 | 1.65 | $258.44 |

## ALIGNMENT × CORRELATION × DTE

Same 2×2 above, split by DTE bucket. Cells with n<20 marked ⚠.

**DTE 0-1**:

| Alignment | Correlation | n | win% | mean | median | PF | total |
|---|---|---:|---:|---:|---:|---:|---:|
| ALIGNED | LOW | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| ALIGNED | HIGH | 74 | 41.9% | $3.04 | $-6.80 | 1.22 | $225.27 |
| MIXED | LOW | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| MIXED | HIGH | 182 | 25.3% | $-11.79 | $-15.32 | 0.45 | $-2,145.39 |
| AGAINST | LOW | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| AGAINST | HIGH | 28 | 35.7% | $4.71 | $-10.82 | 1.39 | $131.88 |

**DTE 2-7**:

| Alignment | Correlation | n | win% | mean | median | PF | total |
|---|---|---:|---:|---:|---:|---:|---:|
| ALIGNED | LOW | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| ALIGNED | HIGH | 59 | 32.2% | $0.16 | $-10.66 | 1.01 | $9.73 |
| MIXED | LOW | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| MIXED | HIGH | 141 | 32.6% | $-5.91 | $-8.32 | 0.61 | $-833.78 |
| AGAINST | LOW | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| AGAINST ⚠ | HIGH | 11 | 54.5% | $6.17 | $1.68 | 2.51 | $67.83 |

**DTE 8-14**:

| Alignment | Correlation | n | win% | mean | median | PF | total |
|---|---|---:|---:|---:|---:|---:|---:|
| ALIGNED | LOW | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| ALIGNED | HIGH | 52 | 28.8% | $9.15 | $-7.32 | 1.60 | $475.64 |
| MIXED | LOW | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| MIXED | HIGH | 68 | 25.0% | $-7.99 | $-10.32 | 0.48 | $-543.46 |
| AGAINST | LOW | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| AGAINST ⚠ | HIGH | 2 | 50.0% | $-1.82 | $-1.82 | 0.70 | $-3.64 |

**DTE 15+**:

| Alignment | Correlation | n | win% | mean | median | PF | total |
|---|---|---:|---:|---:|---:|---:|---:|
| ALIGNED | LOW | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| ALIGNED | HIGH | 96 | 20.8% | $-6.19 | $-9.82 | 0.56 | $-594.01 |
| MIXED | LOW | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| MIXED | HIGH | 102 | 29.4% | $-1.54 | $-6.32 | 0.88 | $-157.04 |
| AGAINST | LOW | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| AGAINST ⚠ | HIGH | 2 | 100.0% | $31.18 | $31.18 | — | $62.37 |

## ALIGNMENT × CORRELATION × MONEYNESS

Same 2×2 above, split by ITM/ATM/OTM (NA excluded from the split itself). Cells with n<20 marked ⚠.

**Moneyness ITM**:

| Alignment | Correlation | n | win% | mean | median | PF | total |
|---|---|---:|---:|---:|---:|---:|---:|
| ALIGNED | LOW | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| ALIGNED ⚠ | HIGH | 17 | 64.7% | $30.66 | $20.68 | 8.24 | $521.22 |
| MIXED | LOW | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| MIXED | HIGH | 30 | 46.7% | $2.12 | $0.00 | 1.23 | $63.60 |
| AGAINST | LOW | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| AGAINST ⚠ | HIGH | 2 | 100.0% | $20.34 | $20.34 | — | $40.69 |

**Moneyness ATM**:

| Alignment | Correlation | n | win% | mean | median | PF | total |
|---|---|---:|---:|---:|---:|---:|---:|
| ALIGNED | LOW | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| ALIGNED | HIGH | 109 | 39.4% | $3.07 | $-7.32 | 1.23 | $334.62 |
| MIXED | LOW | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| MIXED | HIGH | 208 | 27.9% | $-10.49 | $-12.32 | 0.48 | $-2,181.17 |
| AGAINST | LOW | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| AGAINST | HIGH | 24 | 33.3% | $-1.38 | $-12.32 | 0.90 | $-33.15 |

**Moneyness OTM**:

| Alignment | Correlation | n | win% | mean | median | PF | total |
|---|---|---:|---:|---:|---:|---:|---:|
| ALIGNED | LOW | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| ALIGNED | HIGH | 85 | 21.2% | $1.28 | $-9.32 | 1.08 | $109.21 |
| MIXED | LOW | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| MIXED | HIGH | 128 | 24.2% | $-9.70 | $-12.32 | 0.42 | $-1,241.49 |
| AGAINST | LOW | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| AGAINST ⚠ | HIGH | 13 | 61.5% | $15.30 | $22.35 | 6.43 | $198.85 |

## MIXED-REGIME DEEP DIVE — DTE × MONEYNESS (correlation split)

Only trades with alignment == MIXED (n_MIXED_options = 493).

**MIXED × Correlation LOW**:

| DTE | Moneyness | n | win% | mean | median | PF | total |
|---|---|---:|---:|---:|---:|---:|---:|
| 0-1 | ITM | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| 0-1 | ATM | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| 0-1 | OTM | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| 2-7 | ITM | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| 2-7 | ATM | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| 2-7 | OTM | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| 8-14 | ITM | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| 8-14 | ATM | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| 8-14 | OTM | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| 15+ | ITM | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| 15+ | ATM | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| 15+ | OTM | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |

**MIXED × Correlation HIGH**:

| DTE | Moneyness | n | win% | mean | median | PF | total |
|---|---|---:|---:|---:|---:|---:|---:|
| 0-1 | ITM ⚠ | 5 | 60.0% | $8.23 | $7.35 | 2.25 | $41.15 |
| 0-1 | ATM | 142 | 26.8% | $-10.83 | $-14.32 | 0.49 | $-1,537.78 |
| 0-1 | OTM | 24 | 8.3% | $-24.26 | $-20.32 | 0.13 | $-582.25 |
| 2-7 | ITM ⚠ | 9 | 66.7% | $9.32 | $12.35 | 3.35 | $83.89 |
| 2-7 | ATM | 45 | 28.9% | $-11.53 | $-8.64 | 0.40 | $-518.68 |
| 2-7 | OTM | 45 | 31.1% | $-6.40 | $-9.66 | 0.59 | $-288.01 |
| 8-14 | ITM ⚠ | 8 | 50.0% | $8.14 | $1.34 | 2.75 | $65.09 |
| 8-14 | ATM ⚠ | 11 | 36.4% | $-6.32 | $-0.32 | 0.61 | $-69.52 |
| 8-14 | OTM | 21 | 14.3% | $-14.97 | $-16.32 | 0.19 | $-314.38 |
| 15+ | ITM ⚠ | 8 | 12.5% | $-15.82 | $-24.65 | 0.27 | $-126.53 |
| 15+ | ATM ⚠ | 10 | 30.0% | $-5.52 | $-8.32 | 0.56 | $-55.19 |
| 15+ | OTM | 38 | 31.6% | $-1.50 | $-3.33 | 0.85 | $-56.85 |

## MARGINAL — CORRELATION (all option trades)

| Correlation | n | win% | mean | median | PF | total |
|---|---:|---:|---:|---:|---:|---:|
| LOW | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| HIGH | 817 | 29.7% | $-4.04 | $-9.32 | 0.74 | $-3,304.60 |

## MARGINAL — DTE (all option trades)

| DTE | n | win% | mean | median | PF | total |
|---|---:|---:|---:|---:|---:|---:|
| 0-1 | 284 | 30.6% | $-6.30 | $-11.32 | 0.66 | $-1,788.24 |
| 2-7 | 211 | 33.6% | $-3.58 | $-8.32 | 0.76 | $-756.22 |
| 8-14 | 122 | 27.0% | $-0.59 | $-8.49 | 0.96 | $-71.46 |
| 15+ | 200 | 26.0% | $-3.44 | $-6.50 | 0.74 | $-688.68 |

## MARGINAL — MONEYNESS (all option trades with bars)

| Moneyness | n | win% | mean | median | PF | total |
|---|---:|---:|---:|---:|---:|---:|
| ITM | 49 | 55.1% | $12.77 | $7.18 | 2.79 | $625.51 |
| ATM | 341 | 32.0% | $-5.51 | $-10.64 | 0.68 | $-1,879.70 |
| OTM | 226 | 25.2% | $-4.13 | $-9.32 | 0.74 | $-933.43 |

## LARGEST-LOSSES OVERLAP

Top-15 largest realized losses among option grouped trades.

| Ticker | Side | Opened → Closed | Hold | DTE | Moneyness | Corr | Align | Regime | P&L |
|---|---|---|---:|---:|---|---|---|---|---:|
| SPY | P | 2026-08-19 → 2026-08-21 | 2 | 2 | ATM | HIGH | MIXED | MIXED | $-169.98 |
| OKLO | P | 2026-07-17 → 2026-07-17 | 0 | 0 | OTM | HIGH | MIXED | MIXED | $-131.97 |
| SPY | P | 2026-06-24 → 2026-06-24 | 0 | 0 | ATM | HIGH | MIXED | MIXED | $-118.93 |
| ASTS | P | 2026-08-19 → 2026-08-19 | 0 | 2 | OTM | HIGH | MIXED | MIXED | $-112.66 |
| SPY | P | 2026-07-17 → 2026-07-17 | 0 | 0 | ATM | HIGH | MIXED | MIXED | $-109.98 |
| SPY | P | 2026-06-26 → 2026-06-26 | 0 | 0 | ATM | HIGH | MIXED | MIXED | $-108.66 |
| IWM | P | 2026-08-20 → 2026-08-21 | 1 | 1 | NA | HIGH | MIXED | MIXED | $-108.66 |
| SPY | C | 2026-09-10 → 2026-09-10 | 0 | 0 | ATM | HIGH | MIXED | MIXED | $-101.27 |
| SPY | P | 2026-08-19 → 2026-08-20 | 1 | 1 | ATM | HIGH | MIXED | MIXED | $-97.30 |
| NVDA | C | 2026-08-17 → 2026-08-18 | 1 | 4 | OTM | HIGH | MIXED | MIXED | $-96.97 |
| SPY | P | 2026-07-23 → 2026-07-23 | 0 | 0 | ATM | HIGH | MIXED | MIXED | $-90.97 |
| NOW | C | 2026-08-31 → 2026-08-31 | 0 | 4 | ATM | HIGH | MIXED | MIXED | $-82.96 |
| SOFI | C | 2026-07-13 → 2026-07-15 | 2 | 11 | OTM | HIGH | MIXED | MIXED | $-81.63 |
| AAPL | C | 2026-07-27 → 2026-07-27 | 0 | 2 | ATM | HIGH | MIXED | MIXED | $-78.64 |
| INTC | P | 2026-07-28 → 2026-07-28 | 0 | 1 | ATM | HIGH | MIXED | MIXED | $-77.92 |

**Overlap on the top-15 largest option losses**:
- MIXED regime: **15/15**
- CORR_HIGH at open: **15/15**
- Short DTE (0-7): **14/15**
- ATM or OTM: **14/15**
- MIXED + CORR_HIGH: **15/15**
- MIXED + Short DTE: **14/15**
- MIXED + CORR_HIGH + Short DTE: **14/15**
- MIXED + CORR_HIGH + Short DTE + (ATM or OTM): **13/15**

## PREREGISTERED CHECKS

| Check | statistic | passes? |
|---|---|:---:|
| C1: MIXED mean < ALIGNED mean by > $3 (both n >= 20) | MIXED mean $-7.46 (n=493) vs ALIGNED mean $0.42 (n=281) | ✅ |
| C2: MIXED+CORR_HIGH mean < MIXED+CORR_LOW mean by > $3 (both n >= 20) | MIXED+CORR_HIGH mean $-7.46 (n=493) vs MIXED+CORR_LOW mean $0.00 (n=0) | ❌ |
| C3: MIXED+short-DTE(0-7) mean < MIXED+mid/long-DTE(8+) mean by > $3 (both n >= 20) | MIXED+short-DTE mean $-9.22 (n=323) vs MIXED+long-DTE mean $-4.12 (n=170) | ✅ |
| C4: top-15 largest option losses over-represent MIXED+CORR_HIGH at >= 10/15  (observed 15/15) | top-15 overlap = 15/15 | ✅ |

## WHAT SUPPORTS THE HYPOTHESIS

- MIXED regime (n=493, mean $-7.46) loses more per trade than ALIGNED regime (n=281, mean $0.42). Gap $7.88.
- Inside MIXED regime, short-DTE (0-7) mean $-9.22 (n=323) is worse than 8+ DTE mean $-4.12 (n=170).
- Top-15 largest option losses: 15/15 opened during MIXED regime AND with CORR_HIGH.
- Top-15 largest option losses: 15/15 opened during MIXED regime. Concentrated.
- Top-15 losses in the triple-intersection (MIXED + CORR_HIGH + Short-DTE): 14/15.

## WHAT CONTRADICTS OR COMPLICATES THE HYPOTHESIS

- CORR_HIGH fires on 100.0% of option trades — the rule is either too tight or too loose to discriminate cleanly at this book's scale.

## WHAT WE CANNOT CONCLUDE

- **Universal high-load book** — every option trade opened with 3+ other positions active, so there is no true LOW-load counter-example on this sample. Correlation flag captures a specific SHAPE of high-load exposure, not high-load vs low-load.
- **SPY was almost never BEARISH** in this 3-month window (1 of 872 trade opens). MIXED is dominant by construction. The MIXED vs ALIGNED comparison is limited to the trend clarity axis.
- **Causality** — cross-sectional comparison, not randomized. Alignment, correlation, DTE, and moneyness co-vary with unobserved factors (subjective conviction, session time, spread cost).
- **Underlying coverage** — 40 of 152 unique underlyings have bars in cache; the sector-based rule (a) and (b) still applies but the return-correlation rule (c) fires only when both tickers are cached.
- **N-thresholds** — cells with n<20 flagged ⚠; do not treat them as evidence for or against anything.

## FINAL QUESTION — evidence-based answer

**Are my losses better explained by trading in unclear market regimes while stacking correlated short-duration option exposure, rather than by simple directional disagreement with SPY?**

Score across four preregistered checks: **3 / 4** (one check UNTESTABLE — CORR_LOW empty).

- ✅ C1: MIXED mean < ALIGNED mean by > $3 (both n >= 20)
- ❌ C2: MIXED+CORR_HIGH mean < MIXED+CORR_LOW mean by > $3 (both n >= 20)
- ✅ C3: MIXED+short-DTE(0-7) mean < MIXED+mid/long-DTE(8+) mean by > $3 (both n >= 20)
- ✅ C4: top-15 largest option losses over-represent MIXED+CORR_HIGH at >= 10/15  (observed 15/15)

**Testable checks**: 3 of 3 passed.

**Interpretive verdict** (per user's allowed conclusions):

- Mechanical rubric: **insufficient evidence** (one check untestable because CORR_LOW never occurred — every option trade opened into a correlated portfolio).
- On the 3 checks that WERE testable, all passed. The hypothesis's testable components are supported by the data. The remaining component (correlation as an independent driver) is not refuted, only unmeasurable at this book's operating mode.
- **Best defensible reading**: **partially supported** — MIXED regime and short-DTE-inside-MIXED clearly matter and the largest losses concentrate in the MIXED+CORR_HIGH+short-DTE+ATM/OTM intersection, but the correlation flag firing 100% of the time means it cannot be separated from other axes of exposure on this sample.

**Practical read (no rules, no production changes)**:
- All 15 of the largest option losses opened in MIXED SPY regime with a correlated portfolio already active; 14 of 15 also had DTE ≤ 7 and 13 of 15 were ATM/OTM. These four conditions co-occur at the site of the worst outcomes.
- The correlation-flag itself does not discriminate on this book because it fires universally; treating it as a stand-alone risk factor is unsupported at this sample. Correlation exposure is a book-level property of how this account trades, not a per-trade knob that varies.
- Simple 'against SPY' framing (from the prior report) remains not-supported: AGAINST was 5% of trades and profitable on average.

**No production changes.** Diagnosis only.