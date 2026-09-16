# SCHWAB DIAGNOSTIC REPORT


## DATA COVERAGE

- Schwab CSV: `0f1bec32-XXXX1615_GainLoss_Realized_Details_20260916-101658.csv`
- Bars cache: `/tmp/claude-0/-home-user-autonomous-trading-system/7d497cb3-2bdb-560e-915e-2f206b920cf3/scratchpad/bars_cache` (daily bars via `mcp__Agentic_trader__get_equity_historicals`, split-adjusted, RTH only).
- Rows parsed (raw lots): **1311**
- Grouped logical trades (same ticker + side + strike + expiry + opened + closed): **872**
- Equity lots: **69**
- Option lots: **1242**
- Option lots with parsable symbol (strike + expiry + C/P): **1242** (100% — all Schwab option symbols are structured)
- Distinct underlyings across the CSV: **152**
- Underlyings with bars in cache: **40 / 152** (top-40 by lot volume)
- Grouped trades with underlying bars available: **643 / 872** (73.7%)
- Timestamp granularity in the Schwab export: **date-only** (opened/closed dates, no intraday times). Same-day flag is preserved but intraday sequencing is NOT reconstructable from this file.
- Missing / partial fields flagged in the CSV: none — all present rows have opened, closed, quantity, cost, proceeds, gain/loss, wash-sale, disallowed-loss columns.

**Explicit non-availabilities** (do not infer from these):
- Historical PABS scanner rankings — not in this environment.
- Historical Top-10 Watch / Telegram outputs — not in this environment.
- Historical PABS v0.3 context bundles at each entry — the module can compute simple technical features (SMA/MACD/BB/RS) on the cached bars, but not the full 267-field context.
- Intraday bars — MCP daily only; intraday would need explicit fetches per trade date and is out of scope for this pass.

## ACCOUNT / TRADE PROFILE

From the Schwab lot-level export (denominators: `n` in each row).

| Slice | n_lots | W / L / 0 | win% | total P&L | avg win | avg loss | payoff | expectancy/lot |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 1311 | 357/694/260 | 27.2% | $-3,749.71 | $28.22 | $-19.92 | 1.42x | $-2.86 |
| equity | 69 | 7/39/23 | 10.1% | $-445.11 | $4.42 | $-12.21 | 0.36x | $-6.45 |
| options | 1242 | 350/655/237 | 28.2% | $-3,304.60 | $28.70 | $-20.38 | 1.41x | $-2.66 |

- Wash-sale lots: **273** (20.8% of all lots)
- Total disallowed loss: **$5,297.84**

## BEHAVIOR PATTERNS

- Trading window (by close date): **2026-06-16 → 2026-09-16** (93 calendar days, 63 distinct close days).
- Distinct open days: **79** — earliest open **2025-10-14**, latest **2026-09-16**.
- Grouped trades per open-day: mean **11.0**, median **10**, max **32**.
- Top-5 heaviest open-days: 2026-07-01 (32), 2026-07-13 (31), 2026-07-24 (31), 2026-07-15 (30), 2026-07-16 (26)
- Same-day-close grouped trades: **563 / 872** (64.6%). Lot-level equivalent from feedback: 910 of 1,242 option lots (73%).
- Same-ticker + same-side re-entries within 3 trading days: **510** grouped-trade pairs. Of those, **284** followed a losing prior trade (**55.7%**).
- Daily P&L days: **22 positive**, **41 negative** (of 63 close-days). Longest losing-day streak: **9**; longest winning-day streak: **3**.
- Grouped trades opened the trading day AFTER a losing close-day: **447** across **41** losing days (avg **10.9/day**, vs overall mean **11.0/day**).

Instrument mix (grouped trades):
- Options (calls): **568** trades
- Options (puts):  **249** trades
- Equity:          **55** trades
- Grand total realized P&L (grouped, matches lot-level): **$-3,749.71**

## TICKER SELECTION

Top-15 tickers by grouped-trade net P&L. **n_grouped < 5 rows are flagged ⚠ (small sample).**

| Ticker | n_grouped | net P&L | mean | median | win% | profit factor | small-N |
|---|---:|---:|---:|---:|---:|---:|:---:|
| PYPL | 7 | $782.73 | $111.82 | $6.68 | 57.1% | 9.30 |  |
| AAPL | 61 | $292.40 | $4.79 | $-5.99 | 44.3% | 1.39 |  |
| BUG | 7 | $267.11 | $38.16 | $40.68 | 57.1% | 3.80 |  |
| S | 9 | $206.13 | $22.90 | $24.35 | 55.6% | 3.28 |  |
| RPD | 11 | $186.49 | $16.95 | $3.68 | 54.5% | 4.29 |  |
| DAL | 2 | $175.36 | $87.68 | $87.68 | 100.0% | — | ⚠ |
| RKLB | 25 | $165.55 | $6.62 | $0.00 | 44.0% | 1.85 |  |
| BFLY | 1 | $143.68 | $143.68 | $143.68 | 100.0% | — | ⚠ |
| AVAH | 2 | $108.02 | $54.01 | $54.01 | 100.0% | — | ⚠ |
| INNV | 5 | $105.06 | $21.01 | $-16.32 | 40.0% | 2.46 |  |
| SPCX | 5 | $102.25 | $20.45 | $14.20 | 80.0% | 3.45 |  |
| QQQ | 15 | $101.89 | $6.79 | $-11.32 | 33.3% | 1.42 |  |
| KTOS | 4 | $96.72 | $24.18 | $27.18 | 75.0% | 16.30 | ⚠ |
| OTLK | 1 | $86.68 | $86.68 | $86.68 | 100.0% | — | ⚠ |
| IREN | 4 | $81.12 | $20.28 | $24.86 | 75.0% | 4.99 | ⚠ |

Bottom-15 tickers by grouped-trade net P&L:

| Ticker | n_grouped | net P&L | mean | median | win% | profit factor | small-N |
|---|---:|---:|---:|---:|---:|---:|:---:|
| NVTS | 12 | $-96.87 | $-8.07 | $-2.98 | 16.7% | 0.30 |  |
| BBY | 3 | $-103.29 | $-34.43 | $-31.33 | 0.0% | 0.00 | ⚠ |
| KULR | 6 | $-106.72 | $-17.79 | $-10.66 | 16.7% | 0.03 |  |
| QUBT | 10 | $-143.89 | $-14.39 | $-18.32 | 10.0% | 0.02 |  |
| IWM | 2 | $-150.98 | $-75.49 | $-75.49 | 0.0% | 0.00 | ⚠ |
| SOFI | 19 | $-152.74 | $-8.04 | $-11.32 | 21.1% | 0.40 |  |
| TE | 23 | $-152.83 | $-6.64 | $0.00 | 0.0% | 0.00 |  |
| HPQ | 6 | $-156.55 | $-26.09 | $-23.13 | 0.0% | 0.00 |  |
| OKLO | 5 | $-180.57 | $-36.11 | $-15.32 | 20.0% | 0.05 |  |
| QBTS | 15 | $-195.84 | $-13.06 | $-6.99 | 40.0% | 0.24 |  |
| NOW | 5 | $-200.91 | $-40.18 | $-28.67 | 0.0% | 0.00 |  |
| ACHR | 14 | $-201.64 | $-14.40 | $-12.66 | 7.1% | 0.06 |  |
| ASTS | 13 | $-214.18 | $-16.48 | $-14.32 | 23.1% | 0.23 |  |
| NVDA | 62 | $-326.60 | $-5.27 | $-10.82 | 35.5% | 0.70 |  |
| SPY | 134 | $-1,828.11 | $-13.64 | $-15.32 | 23.1% | 0.41 |  |

**Not conclusions**: a ticker being profitable at n=5 is not evidence of skill on that ticker; a ticker being unprofitable at n=5 is not evidence of a bad ticker. Small-n rows are diagnostic only.

## UNDERLYING PRICE OUTCOMES

Denominator: **616** option grouped trades where the underlying has daily bars in cache.
Limitation: daily granularity — an intraday round-trip on a 0DTE option can miss the peak/trough the underlying prints inside the same session. Numbers below reflect daily closes only. Do not read intraday precision into them.
Underlying move IN THE TRADE DIRECTION (long for calls, short for puts):
- Forward 1-day (open→next close): n=608, mean -0.31%, median -0.14%, favorable-direction rate 44.9%
- Forward 3-day: n=601, mean -0.50%, median -0.28%, favorable-direction rate 45.8%
- Forward 5-day: n=597, mean -1.16%, median -0.55%, favorable-direction rate 42.9%
- Underlying MFE during hold (daily-only): mean **4.70%**, median **2.66%** (n=161).
- Underlying MAE during hold (daily-only): mean **-3.58%**, median **-3.03%** (n=161).

**Note on same-day options**: for grouped trades opened AND closed the same day, `hold_days == 0` so daily-bar MFE/MAE returns nothing (there is no bar *after* open and *before or on* close by daily definition). Those show as `None` above and are excluded from MFE/MAE averages.

## GOOD IDEA / BAD EXECUTION CASES

Diagnostic classification, NOT causal proof. Buckets defined on daily closes only.

Denominator: **161** option trades with a same-day-or-later exit bar available.

| Bucket | Description | n | share |
|---|---|---:|---:|
| **A** | underlying favorable AND option made money — 'idea+execution both worked' | 42 | 26.1% |
| **B** | underlying favorable BUT option LOST — 'right thesis, wrong contract/timing' | 29 | 18.0% |
| **C** | underlying unfavorable BUT option made money — 'wrong thesis, saved by luck or short-dated pop' | 8 | 5.0% |
| **D** | underlying unfavorable AND option lost — 'thesis wrong' | 82 | 50.9% |

**Guardrails**:
- The 'favorable at exit' flag is measured on the underlying's CLOSE on the exit date vs the underlying's CLOSE on the entry date. For same-day closes, `hold_days == 0` → no next-close available → those trades are excluded from this table (see the denominator).
- Do NOT read causality into this. B ≠ proof of execution failure; A ≠ proof of skill. Big B share does raise the QUESTION of contract/timing selection.

## OPTION EXECUTION

Same-day-close and DTE cuts below are on grouped option trades.

**DTE EFFECTS** (denominator = grouped option trades with a parsable expiry):

| DTE at open | n | net P&L | mean | median | win% | profit factor |
|---|---:|---:|---:|---:|---:|---:|
| 0DTE | 179 | $-730.14 | $-4.08 | $-11.32 | 31.8% | 0.78 |
| 1DTE | 105 | $-1,058.10 | $-10.08 | $-11.32 | 28.6% | 0.44 |
| 2-3 | 116 | $-366.61 | $-3.16 | $-7.83 | 37.1% | 0.78 |
| 4-7 | 95 | $-389.61 | $-4.10 | $-8.64 | 29.5% | 0.73 |
| 8-14 | 122 | $-71.46 | $-0.59 | $-8.49 | 27.0% | 0.96 |
| 15-30 | 68 | $-150.70 | $-2.22 | $-6.32 | 29.4% | 0.84 |
| 31+ | 132 | $-537.98 | $-4.08 | $-8.32 | 24.2% | 0.69 |

**Same-day vs multi-day option grouped trades**:

| Slice | n | net P&L | mean | median | win% | profit factor |
|---|---:|---:|---:|---:|---:|---:|
| Same-day | 554 | $-2,465.96 | $-4.45 | $-9.32 | 30.3% | 0.70 |
| Multi-day | 263 | $-838.64 | $-3.19 | $-11.32 | 28.5% | 0.82 |

**1-contract vs multi-contract grouped option trades**:

| Slice | n | net P&L | mean | median | win% | profit factor |
|---|---:|---:|---:|---:|---:|---:|
| 1 contract | 472 | $-1,497.51 | $-3.17 | $-7.33 | 28.4% | 0.74 |
| 2+ contracts | 345 | $-1,807.09 | $-5.24 | $-14.66 | 31.6% | 0.75 |

## SPY VS INDIVIDUAL NAMES

| Slice | n | net P&L | mean | median | win% | profit factor |
|---|---:|---:|---:|---:|---:|---:|
| Index options (SPY/QQQ/IWM) | 151 | $-1,877.20 | $-12.43 | $-15.32 | 23.8% | 0.46 |
| Individual-name options | 666 | $-1,427.40 | $-2.14 | $-7.99 | 31.1% | 0.85 |
| SPY options only | 134 | $-1,828.11 | $-13.64 | $-15.32 | 23.1% | 0.41 |
| Non-SPY options | 683 | $-1,476.49 | $-2.16 | $-8.32 | 31.0% | 0.85 |

## SAME-DAY / RE-ENTRY EFFECTS

| Slice | n | net P&L | mean | median | win% | profit factor |
|---|---:|---:|---:|---:|---:|---:|
| First attempt | 291 | $-1,671.81 | $-5.75 | $-13.97 | 29.9% | 0.67 |
| Re-entry within 5 days (same ticker + side) | 526 | $-1,632.79 | $-3.10 | $-7.99 | 29.7% | 0.79 |

## SIMPLE TECHNICAL BACKTESTS

Preregistered simple features computed at entry-day close. **These are not permanent rules.** Do not build a model on a single 3-month sample.

| Feature | n_trades_with_feature | net P&L | mean | median | win% | profit factor | vs. all-option baseline |
|---|---:|---:|---:|---:|---:|---:|---:|
| Underlying close > SMA20 at entry | 337 | $82.19 | $0.24 | $-8.32 | 33.8% | 1.02 | $4.29 |
| Underlying close > SMA50 at entry | 375 | $-168.27 | $-0.45 | $-9.33 | 32.3% | 0.97 | $3.60 |
| Underlying close > SMA200 at entry | 426 | $-2,095.43 | $-4.92 | $-10.48 | 30.8% | 0.72 | $-0.87 |
| MACD line above signal at entry | 291 | $-84.95 | $-0.29 | $-8.32 | 34.4% | 0.98 | $3.75 |
| Fresh MACD cross UP within last 3 bars | 75 | $-159.39 | $-2.13 | $-6.32 | 38.7% | 0.86 | $1.92 |
| Fresh MACD cross DOWN within last 3 bars | 41 | $-475.69 | $-11.60 | $-8.64 | 24.4% | 0.35 | $-7.56 |
| BB width in bottom quintile of last 60 bars | 228 | $-1,698.98 | $-7.45 | $-11.98 | 28.9% | 0.57 | $-3.41 |
| Close within 1% of trailing 20-day high | 78 | $474.28 | $6.08 | $-4.32 | 39.7% | 1.52 | $10.13 |
| Close within 1% of trailing 20-day low | 35 | $-167.55 | $-4.79 | $-6.32 | 45.7% | 0.73 | $-0.74 |

All-option baseline (for comparison): n=817, mean **$-4.04**, win% **29.7%**, profit factor **0.74**.

## INFLECTION-POINT HYPOTHESIS

Five preregistered predicates, evaluated on the option grouped trades that have entry-day bars. **Do not treat these as production rules.**

| Hypothesis | n | net P&L | mean | median | win% | profit factor | fwd-1d underlying mean | fwd-5d underlying mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A: fresh MACD cross (side-aligned) | 88 | $-456.53 | $-5.19 | $-8.48 | 35.2% | 0.69 | 0.29% | 0.41% |
| B: A + BB compression | 45 | $-270.85 | $-6.02 | $-6.32 | 37.8% | 0.66 | 0.12% | 0.15% |
| C: A + near recent support/resistance ⚠ small-N | 0 | $0.00 | $0.00 | $0.00 | 0.0% | — | — | — |
| D: A + RS-vs-SPY on side | 22 | $-196.95 | $-8.95 | $-6.99 | 31.8% | 0.47 | 0.34% | 0.20% |
| E: B + D (compression + RS + fresh cross) ⚠ small-N | 12 | $-60.78 | $-5.07 | $-6.32 | 33.3% | 0.65 | 0.68% | 2.06% |

## SEPARATE THREE FAILURE TYPES

Score of the evidence — qualitative, not causal.

**SELECTION** — did the underlying move the intended way?
- Denominator (option trades where underlying exit close is available): **161**.
- Underlying moved AGAINST the trade direction at exit: **90 / 161** (55.9%).
- Underlying moved WITH the trade direction at exit: **71 / 161** (44.1%).
- Forward-1-day favorable-direction rate across all option trades w/ bars: **44.9%**.
- Forward-5-day favorable-direction rate: **42.9%**.
- Read: below-coin-flip favorable-direction rate at 1d/5d indicates the underlying often did not move the intended way after entry. Selection is under pressure.

**EXECUTION** — right thesis, wrong outcome?
- Bucket B (underlying favorable at exit, option lost): **29 / 161** (18.0%) of trades with bars.
- For context: bucket A (both worked) = 42 / 161 (26.1%); D (both wrong) = 82 / 161 (50.9%).
- Read: bucket B is the direct execution-failure signal. On daily granularity, it accounts for a MINORITY of losing trades relative to bucket D. Execution failure is present but not the dominant explanation on this sample.
- Caveat: same-day trades (554 grouped trades) are NOT in this denominator (no daily-bar exit). If the intraday round-trip on those went well on the underlying but badly on the option, that would boost B and this attribution would shift. Intraday bars are the next step to resolve this.

**BEHAVIOR / RISK** — amplified by process?
- Trades per open-day: mean **11.0**, max **32**. Very heavy days concentrated in Jul 2026 (top-5 days all Jul).
- Same-day-close share: **64.6%** of grouped trades (lot-level: 73%).
- 0-1 DTE share of the losing-option $ (of losing grouped-option trades): **40.9%** — see 'WHAT LOOKS MOST DAMAGING'.
- Re-entries within 3 days after a loss: **284 / 510** re-entry pairs (55.7%).
- Trading frequency the day AFTER a losing close-day: **10.9/day** vs overall mean **11.0/day**. NOT elevated on this sample — no clear post-loss revenge spike, though re-entry share within 3 days remains high.
- Longest losing-day streak: **9** consecutive close-days.
- Read: behavior/risk factors (same-day / short-DTE / concentration / re-entry) coincide with the highest-loss rows. Whether they CAUSE the loss or just AMPLIFY a selection problem is not separable from this sample alone.

**Overall attribution — the honest verdict on this 3-month sample**:
- The **D bucket (thesis wrong AND option lost)** is the largest single class of trades with bars (82 of 161). That is a **selection-heavy** signature.
- The **B bucket (right thesis, wrong option)** is real but smaller (29 of 161). Execution failure is present, not primary.
- **Behavior/risk factors** — same-day, 0-1 DTE, SPY concentration — align with the largest dollar losses. On the same sample they cannot be separated from selection: a bad thesis executed via 0DTE loses more than a bad thesis executed via 30DTE, but the thesis was still wrong.
- **Conclusion category**: **multiple factors are material** (selection appears somewhat dominant on daily-bar evidence, behavior/risk amplifies it, execution failure exists but is not primary). Wait for the next 3-month window before hardening any single reading.

## WHAT LOOKS MOST DAMAGING

- Total realized LOSS on losing option grouped trades: $-12,888.37
- SPY-only share of that loss: $-3,108.74 (24.1%)
- Same-day-close option share: $-8,199.78 (63.6%)
- 0-1 DTE share: $-5,269.51 (40.9%)

Note the overlap: same-day + 0-1 DTE + SPY all describe the same subset of behavior in many rows. These are not four independent explanations.

## WHAT LOOKS PROMISING

Rows to inspect further (not conclusions):
- Multi-day option grouped trades (n=263) show a materially better mean than same-day (see 'Same-day vs multi-day' table).
- Individual-name options meaningfully outperform index (SPY/QQQ/IWM) options on the mean, but concentration still matters — the top few names dominate.
- Hypothesis A (fresh MACD cross side-aligned) and D (adding RS on your side) are the two inflection tests with the least catastrophic n; both need repetition across more months before treating as edge.

## WHAT WE CANNOT CONCLUDE

Given only 3 months of realized-lot data plus daily bars:
- **Intraday sequencing / execution slippage** — the CSV is date-only; whether losses came from bad entry price, bad exit price, or spread cost is not decidable here.
- **Whether PABS setup context predicted these trades** — no historical PABS state is available in this environment. Any 'PABS said X' claim is not defensible from this data.
- **Ticker-level edge** — 3 months is too short to declare any ticker an edge or a curse. All ticker rows are diagnostic; small-N flagged.
- **Options-vs-stock counterfactual** — did the *stock* trade have worked? The CSV shows only what happened. The underlying-outcome section is a **hypothetical** on the underlying move, not the trade you actually made.
- **Options structure sensitivity** — moneyness (ITM/ATM/OTM) is not analyzed here (strike-vs-spot at entry would need extra fetches). That is a genuine next step, not a claim.
- **Regime interaction** — SPY was broadly rising over this window on daily closes; whether puts underperformed because of a bearish thesis in a rising tape vs. genuinely bad selection is not separable at 3 months.

## NEXT RESEARCH STEP

Ordered by cost-to-value, no code changes to production:
1. **Extend the cache** to the long-tail 112 tickers (currently at 40; ~24% of trades are outside the cache). Uniform coverage removes selection artifacts in the per-ticker table.
2. **Add option-structure fields** — at entry, compute moneyness (strike/spot − 1) and label each trade OTM/ATM/ITM. Rebucket P&L by moneyness × DTE. This is where 'right thesis, wrong contract' most often shows up.
3. **Fetch intraday 5m or 1m bars for a random sample of 100 same-day-close trades** — daily bars can't tell you whether you got in on a high and out on a low, or vice versa. This is the direct test for execution failure.
4. **Rerun on the next 3 months as they land.** All conclusions above are provisional at n≈300 grouped trades. The stability of the findings across a second, out-of-sample window is what matters.
5. **Only after (2)-(4)**: build the setup-tag join (research/context.compute_context_at at entry) so PABS can produce a real 'setup-conditional expectancy' for this trader. Not until.

**Not next steps** (explicitly): no whitelist, no permanent ticker bans, no composite score, no production rule changes, no threshold optimization on this same sample.