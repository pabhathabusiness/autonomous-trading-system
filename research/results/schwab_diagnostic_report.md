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

## UNDERLYING-MOVE vs OPTION-P&L QUADRANTS (P5, was 'GOOD IDEA / BAD EXECUTION')

Descriptive quadrants only. **Labels are 'session-outcome × option-outcome', with no causal claim.** ('luck' and 'wrong thesis' language removed per P5.)

Denominator: **161** option trades with a same-day-or-later exit bar available (multi-day only — daily granularity cannot classify same-day trades this way; use the intraday sample section for those).

| Quadrant | Underlying (exit close vs entry close) | Option realized P&L | n | share |
|---|---|---|---:|---:|
| A | favorable (moved with trade side) | POSITIVE | 42 | 26.1% |
| B | favorable | NEGATIVE | 29 | 18.0% |
| C | unfavorable | POSITIVE | 8 | 5.0% |
| D | unfavorable | NEGATIVE | 82 | 50.9% |

**Guardrails**:
- Same-day trades are NOT in this denominator; they need intraday bars (see P3 section).
- 'Favorable at exit' is measured on daily close vs daily close only; intraday drawdowns/rebounds are invisible here.
- Quadrant B is a NECESSARY-but-not-sufficient marker for contract/timing failure. It is not proof of execution failure.
- Quadrant C is a NECESSARY-but-not-sufficient marker for a mis-attributed win; it is not proof the thesis was wrong. Some Cs are due to option delta/gamma mechanics against a small underlying move.

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

## MONEYNESS AT ENTRY (P1)

Denominator: **616** option grouped trades with entry-day underlying spot available in the cache.
Definition: `pct = signed % ITM`. Calls: `(spot − strike)/strike × 100`. Puts: `(strike − spot)/strike × 100`. Buckets: **ITM_deep ≥ +5%**, ITM +2% to +5%, ATM ±2%, OTM −5% to −2%, OTM_deep ≤ −5%. Neutral by construction between calls and puts.

| Moneyness bucket | n | net P&L | mean | median | win% | profit factor |
|---|---:|---:|---:|---:|---:|---:|
| ITM_deep | 11 | $128.14 | $11.65 | $0.00 | 45.5% | 2.08 |
| ITM | 38 | $497.37 | $13.09 | $7.26 | 57.9% | 3.15 |
| ATM | 341 | $-1,879.70 | $-5.51 | $-10.64 | 32.0% | 0.68 |
| OTM | 104 | $-1,044.69 | $-10.05 | $-10.31 | 28.8% | 0.47 |
| OTM_deep | 122 | $111.26 | $0.91 | $-7.32 | 22.1% | 1.07 |

- Median moneyness pct across all trades: **-0.87%** (positive = ITM).
- Fraction ITM (any degree): **8.0%**; ATM: **55.4%**; OTM (any degree): **36.7%**.

## DTE CONDITIONED ON UNDERLYING OUTCOME (P2)

Split option trades that HAVE an underlying exit-close available (n=161) into 'underlying moved favorably' vs 'unfavorably' by exit-day close vs entry-day close. Within each, rebucket by DTE at open. Question: does short DTE destroy otherwise-correct ideas?

**Underlying moved FAVORABLY at exit close** (bucket A + B):

| DTE | n | net P&L | mean | median | win% | profit factor |
|---|---:|---:|---:|---:|---:|---:|
| 0-1 ⚠ | 2 | $-112.96 | $-56.48 | $-56.48 | 0.0% | 0.00 |
| 2-7 ⚠ | 12 | $178.19 | $14.85 | $5.20 | 58.3% | 1.75 |
| 8-14 | 22 | $936.64 | $42.57 | $10.00 | 54.5% | 5.54 |
| 15-30 ⚠ | 13 | $148.57 | $11.43 | $3.68 | 53.8% | 2.17 |
| 31+ | 22 | $488.26 | $22.19 | $19.68 | 72.7% | 12.37 |

**Underlying moved UNFAVORABLY at exit close** (bucket C + D):

| DTE | n | net P&L | mean | median | win% | profit factor |
|---|---:|---:|---:|---:|---:|---:|
| 0-1 ⚠ | 2 | $-84.31 | $-42.16 | $-42.16 | 0.0% | 0.00 |
| 2-7 | 27 | $-707.10 | $-26.19 | $-18.64 | 11.1% | 0.06 |
| 8-14 | 19 | $-424.35 | $-22.33 | $-32.67 | 10.5% | 0.34 |
| 15-30 ⚠ | 10 | $-176.52 | $-17.65 | $-18.82 | 20.0% | 0.07 |
| 31+ | 32 | $-460.74 | $-14.40 | $-15.32 | 3.1% | 0.10 |

Read: **within favorable-underlying trades, compare win% across DTE**. If short-DTE win% is materially below long-DTE win% on the FAVORABLE subset, that is evidence that short DTE destroys otherwise-correct ideas.

## INTRADAY SAMPLE — 100 SAME-DAY OPTION TRADES (P3)

Deterministic sample (hash-sorted): **100** same-day option grouped trades.
Intraday reconstructions available (≥5 RTH bars on entry date): **100 / 100**.
Intraday interval used: **10minute** (server auto-selected for a 3-month range; the user request was 5m, but the range × granularity would have exceeded upstream's bar cap — 10m preserves intraday direction and MFE/MAE fidelity).
**Timing assumption**: the Schwab CSV has no intraday timestamps. All 'entry' metrics below assume entry ≈ session open and 'exit' ≈ session close for the sampled trades. This is an approximation; a real intraday entry-time would sharpen everything below.

**Session-level intraday summaries** (n varies by field; each row shows its own denominator):

| Field | n | mean | median | notes |
|---|---:|---:|---:|---|
| Session return (open → close, trade-direction-signed) | 100 | -0.00% | 0.03% | positive = underlying moved in trade direction over session |
| MFE from session open, %  | 100 | 2.66% | 1.61% | best excursion in trade direction |
| MAE from session open, %  | 100 | -1.22% | -0.86% | worst excursion opposite trade direction |
| Entry location in session range | 100 | 0.49 | 0.52 | 0 = at day's low, 1 = at day's high |
| Gap-open vs prior daily close, %  | 79 | -0.14% | 0.09% | signed gap |
| Prior 3-day return through prev close, %  | 79 | 0.39% | 0.53% | context: was the name already running? |

- Favorable-direction rate at session close: **66/100 = 66.0%**.
- Extended-move-at-open flag (prior-3d > +5% OR |gap| > 2%): **18/100 = 18.0%** of sampled trades.

**P&L split by extended-move-at-open flag** (option grouped-trade P&L, not underlying return):

| Slice | n | net P&L | mean | median | win% |
|---|---:|---:|---:|---:|---:|
| Extended at open (chased?) | 18 | $-209.34 | $-11.63 | $-13.16 | 33.3% |
| Not extended | 61 | $85.05 | $1.39 | $-7.32 | 39.3% |

**P&L split by intraday session direction** (option grouped-trade P&L):

| Underlying session moved | n | net P&L | mean | median | win% |
|---|---:|---:|---:|---:|---:|
| With trade side (favorable) | 66 | $387.16 | $5.87 | $-3.48 | 40.9% |
| Against trade side (unfavorable) | 34 | $-578.92 | $-17.03 | $-13.82 | 20.6% |

**Same-day intraday A/B/C/D-style split (sampled 100)** — descriptive labels only:

| Cell | Definition | n | share |
|---|---|---:|---:|
| A' | session-favorable AND option won | 27 | 27.8% |
| B' | session-favorable AND option lost | 37 | 38.1% |
| C' | session-unfavorable AND option won | 7 | 7.2% |
| D' | session-unfavorable AND option lost | 26 | 26.8% |

**Read**: B' is the cell that, if large, points to the option contract failing to capture an otherwise-correct underlying move (or entry/exit timing inside the session). The sampled-100 estimate here is the closest evidence available in this environment for the 'good idea, bad execution / bad contract' hypothesis on the same-day book.

## SPY VS INDIVIDUAL NAMES, WITH CONTROLS (P4)

Compare SPY grouped option trades to individual-name grouped option trades AFTER controlling for DTE bucket × call/put × moneyness bucket × same-day status. Cells with n_SPY < 3 OR n_individual < 3 are marked ⚠ small-n and excluded from the summary line.

| DTE | Side | Moneyness | Hold | n_SPY | mean_SPY | n_ind | mean_ind | Δ(SPY-ind) | flag |
|---|---|---|---|---:|---:|---:|---:|---:|:---:|
| 0-1 | C | ATM | same_day | 45 | $-12.55 | 54 | $10.68 | $-23.23 |  |
| 0-1 | C | ITM | same_day | 0 | $0.00 | 3 | $56.91 | $0.00 | ⚠ |
| 0-1 | C | NA | same_day | 0 | $0.00 | 9 | $-4.98 | $0.00 | ⚠ |
| 0-1 | C | OTM | same_day | 0 | $0.00 | 18 | $-27.54 | $0.00 | ⚠ |
| 0-1 | C | OTM_deep | multi_day | 0 | $0.00 | 1 | $-15.66 | $0.00 | ⚠ |
| 0-1 | C | OTM_deep | same_day | 0 | $0.00 | 6 | $-13.88 | $0.00 | ⚠ |
| 0-1 | P | ATM | multi_day | 2 | $-82.97 | 0 | $0.00 | $0.00 | ⚠ |
| 0-1 | P | ATM | same_day | 72 | $-9.92 | 37 | $-13.14 | $3.22 |  |
| 0-1 | P | ITM | same_day | 0 | $0.00 | 6 | $12.19 | $0.00 | ⚠ |
| 0-1 | P | NA | same_day | 0 | $0.00 | 4 | $33.93 | $0.00 | ⚠ |
| 0-1 | P | OTM | same_day | 0 | $0.00 | 11 | $-11.17 | $0.00 | ⚠ |
| 0-1 | P | OTM_deep | multi_day | 0 | $0.00 | 1 | $-15.66 | $0.00 | ⚠ |
| 0-1 | P | OTM_deep | same_day | 0 | $0.00 | 2 | $-18.15 | $0.00 | ⚠ |
| 15-30 | C | ATM | multi_day | 0 | $0.00 | 5 | $-4.65 | $0.00 | ⚠ |
| 15-30 | C | ATM | same_day | 0 | $0.00 | 5 | $-7.72 | $0.00 | ⚠ |
| 15-30 | C | ITM | multi_day | 0 | $0.00 | 2 | $-26.81 | $0.00 | ⚠ |
| 15-30 | C | ITM | same_day | 0 | $0.00 | 2 | $12.68 | $0.00 | ⚠ |
| 15-30 | C | NA | multi_day | 0 | $0.00 | 13 | $4.89 | $0.00 | ⚠ |
| 15-30 | C | NA | same_day | 0 | $0.00 | 12 | $-7.57 | $0.00 | ⚠ |
| 15-30 | C | OTM | multi_day | 0 | $0.00 | 7 | $9.25 | $0.00 | ⚠ |
| 15-30 | C | OTM | same_day | 0 | $0.00 | 4 | $6.26 | $0.00 | ⚠ |
| 15-30 | C | OTM_deep | multi_day | 0 | $0.00 | 4 | $-14.40 | $0.00 | ⚠ |
| 15-30 | C | OTM_deep | same_day | 0 | $0.00 | 8 | $-14.61 | $0.00 | ⚠ |
| 15-30 | P | ATM | multi_day | 0 | $0.00 | 1 | $22.35 | $0.00 | ⚠ |
| 15-30 | P | ITM_deep | multi_day | 0 | $0.00 | 1 | $-14.32 | $0.00 | ⚠ |
| 15-30 | P | NA | multi_day | 0 | $0.00 | 1 | $9.68 | $0.00 | ⚠ |
| 15-30 | P | OTM_deep | multi_day | 0 | $0.00 | 3 | $11.24 | $0.00 | ⚠ |
| 2-7 | C | ATM | multi_day | 3 | $-44.32 | 10 | $23.95 | $-68.27 |  |
| 2-7 | C | ATM | same_day | 6 | $-3.88 | 32 | $-1.04 | $-2.84 |  |
| 2-7 | C | ITM | multi_day | 0 | $0.00 | 2 | $-2.07 | $0.00 | ⚠ |
| 2-7 | C | ITM | same_day | 0 | $0.00 | 3 | $14.40 | $0.00 | ⚠ |
| 2-7 | C | ITM_deep | same_day | 0 | $0.00 | 3 | $25.34 | $0.00 | ⚠ |
| 2-7 | C | NA | multi_day | 0 | $0.00 | 11 | $6.18 | $0.00 | ⚠ |
| 2-7 | C | NA | same_day | 0 | $0.00 | 24 | $-1.22 | $0.00 | ⚠ |
| 2-7 | C | OTM | multi_day | 0 | $0.00 | 5 | $-32.51 | $0.00 | ⚠ |
| 2-7 | C | OTM | same_day | 0 | $0.00 | 21 | $-9.13 | $0.00 | ⚠ |
| 2-7 | C | OTM_deep | multi_day | 0 | $0.00 | 8 | $-13.49 | $0.00 | ⚠ |
| 2-7 | C | OTM_deep | same_day | 0 | $0.00 | 11 | $-7.96 | $0.00 | ⚠ |
| 2-7 | P | ATM | multi_day | 3 | $-56.66 | 2 | $-30.30 | $-26.36 | ⚠ |
| 2-7 | P | ATM | same_day | 1 | $0.00 | 13 | $0.65 | $-0.65 | ⚠ |
| 2-7 | P | ITM | multi_day | 0 | $0.00 | 1 | $-11.32 | $0.00 | ⚠ |
| 2-7 | P | ITM | same_day | 0 | $0.00 | 3 | $9.82 | $0.00 | ⚠ |
| 2-7 | P | ITM_deep | same_day | 0 | $0.00 | 1 | $40.35 | $0.00 | ⚠ |
| 2-7 | P | NA | multi_day | 0 | $0.00 | 2 | $7.02 | $0.00 | ⚠ |
| 2-7 | P | NA | same_day | 0 | $0.00 | 10 | $-11.35 | $0.00 | ⚠ |
| 2-7 | P | OTM | multi_day | 0 | $0.00 | 2 | $-15.82 | $0.00 | ⚠ |
| 2-7 | P | OTM | same_day | 0 | $0.00 | 15 | $-3.20 | $0.00 | ⚠ |
| 2-7 | P | OTM_deep | multi_day | 0 | $0.00 | 3 | $-15.44 | $0.00 | ⚠ |
| 2-7 | P | OTM_deep | same_day | 0 | $0.00 | 12 | $2.43 | $0.00 | ⚠ |
| 31+ | C | ATM | multi_day | 0 | $0.00 | 5 | $-8.52 | $0.00 | ⚠ |
| 31+ | C | ITM_deep | multi_day | 0 | $0.00 | 5 | $-7.52 | $0.00 | ⚠ |
| 31+ | C | ITM_deep | same_day | 0 | $0.00 | 1 | $63.68 | $0.00 | ⚠ |
| 31+ | C | NA | multi_day | 0 | $0.00 | 51 | $-7.71 | $0.00 | ⚠ |
| 31+ | C | NA | same_day | 0 | $0.00 | 12 | $-7.18 | $0.00 | ⚠ |
| 31+ | C | OTM | multi_day | 0 | $0.00 | 6 | $15.84 | $0.00 | ⚠ |
| 31+ | C | OTM | same_day | 0 | $0.00 | 2 | $4.68 | $0.00 | ⚠ |
| 31+ | C | OTM_deep | multi_day | 0 | $0.00 | 36 | $1.69 | $0.00 | ⚠ |
| 31+ | C | OTM_deep | same_day | 0 | $0.00 | 6 | $-11.60 | $0.00 | ⚠ |
| 31+ | P | ITM | multi_day | 0 | $0.00 | 2 | $-24.16 | $0.00 | ⚠ |
| 31+ | P | NA | multi_day | 0 | $0.00 | 3 | $-21.77 | $0.00 | ⚠ |
| 31+ | P | NA | same_day | 0 | $0.00 | 3 | $-8.00 | $0.00 | ⚠ |
| 8-14 | C | ATM | multi_day | 1 | $-51.33 | 14 | $-26.10 | $-25.23 | ⚠ |
| 8-14 | C | ATM | same_day | 1 | $-5.33 | 11 | $1.61 | $-6.94 | ⚠ |
| 8-14 | C | ITM | multi_day | 0 | $0.00 | 6 | $39.62 | $0.00 | ⚠ |
| 8-14 | C | ITM | same_day | 0 | $0.00 | 4 | $0.76 | $0.00 | ⚠ |
| 8-14 | C | NA | multi_day | 0 | $0.00 | 15 | $-6.57 | $0.00 | ⚠ |
| 8-14 | C | NA | same_day | 0 | $0.00 | 23 | $-10.04 | $0.00 | ⚠ |
| 8-14 | C | OTM | multi_day | 0 | $0.00 | 5 | $-18.25 | $0.00 | ⚠ |
| 8-14 | C | OTM | same_day | 0 | $0.00 | 7 | $-10.23 | $0.00 | ⚠ |
| 8-14 | C | OTM_deep | multi_day | 0 | $0.00 | 7 | $111.06 | $0.00 | ⚠ |
| 8-14 | C | OTM_deep | same_day | 0 | $0.00 | 8 | $-12.03 | $0.00 | ⚠ |
| 8-14 | P | ATM | multi_day | 0 | $0.00 | 2 | $13.02 | $0.00 | ⚠ |
| 8-14 | P | ATM | same_day | 0 | $0.00 | 1 | $5.68 | $0.00 | ⚠ |
| 8-14 | P | ITM | multi_day | 0 | $0.00 | 1 | $20.68 | $0.00 | ⚠ |
| 8-14 | P | ITM | same_day | 0 | $0.00 | 3 | $3.79 | $0.00 | ⚠ |
| 8-14 | P | NA | multi_day | 0 | $0.00 | 3 | $-23.32 | $0.00 | ⚠ |
| 8-14 | P | NA | same_day | 0 | $0.00 | 3 | $-3.32 | $0.00 | ⚠ |
| 8-14 | P | OTM | same_day | 0 | $0.00 | 1 | $-23.64 | $0.00 | ⚠ |
| 8-14 | P | OTM_deep | multi_day | 0 | $0.00 | 5 | $-8.32 | $0.00 | ⚠ |
| 8-14 | P | OTM_deep | same_day | 0 | $0.00 | 1 | $-15.32 | $0.00 | ⚠ |

**Controlled comparison across 4 cells with n≥3 on both sides**: mean-of-means (weighted by cell size) SPY − individual = **$-11.37** per trade.

**Read**: SPY still underperforms individual names inside the same cell after controlling for DTE × side × moneyness × same-day status. Do NOT conclude SPY is inherently harmful; conclude that within this trader's book, SPY setups paid worse than same-shape non-SPY setups on this sample.

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

## INFLECTION-POINT FEATURES — SEPARATED (P6)

Each base feature reported ON ITS OWN before any combination. All computed at entry-day close, on option grouped trades with adequate historical data (`≥ 60 bars of history for BB percentile / RS`; `≥ 30 for MACD state`; SMA reads their own minimums). Small N (< 20) flagged ⚠.

| Feature (side-aligned) | n TRUE / FALSE / UNAVAIL | mean_TRUE / FALSE | win%_TRUE / FALSE | PF_TRUE / FALSE | fwd-1d TRUE | fwd-5d TRUE |
|---|---:|---:|---:|---:|---:|---:|
| Fresh MACD cross within 3 bars | 88 / 528 / 0 | $-5.19 / $-3.28 | 35.2% / 30.7% | 0.69 / 0.79 | 0.29% | 0.41% |
| BB compression (bottom quintile 60-bar) | 228 / 388 / 0 | $-7.45 / $-1.26 | 28.9% / 32.7% | 0.57 / 0.92 | -0.31% | -1.06% |
| Near recent support/resistance (long ↔ low, short ↔ high) | 21 / 595 / 0 | $-13.06 / $-3.22 | 23.8% / 31.6% | 0.30 / 0.80 | 1.03% | 2.13% |
| Relative strength on trade side | 265 / 351 / 0 | $1.34 / $-7.25 | 35.8% / 27.9% | 1.10 / 0.59 | -0.35% | -1.88% |

**Combinations** (side-aligned in every case). Uses the individual predicates above.

| Combination (side-aligned) | n | net P&L | mean | median | win% | profit factor |
|---|---:|---:|---:|---:|---:|---:|
| Cross + Compression | 45 | $-270.85 | $-6.02 | $-6.32 | 37.8% | 0.66 |
| Cross + Near S/R ⚠ | 0 | $0.00 | $0.00 | $0.00 | 0.0% | — |
| Cross + RS | 22 | $-196.95 | $-8.95 | $-6.99 | 31.8% | 0.47 |
| Cross + Compression + RS ⚠ | 12 | $-60.78 | $-5.07 | $-6.32 | 33.3% | 0.65 |
| Cross + Compression + Near S/R + RS (all 4) ⚠ | 0 | $0.00 | $0.00 | $0.00 | 0.0% | — |

Small-N flags (⚠) mean the row is diagnostic only — do not treat it as evidence for or against the combination. Do not use these to build a rule.

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

**FINAL QUESTION**: 'When I lose, is it more often because the underlying idea was poor, because I entered/exited badly, or because the option contract structure failed to capture an otherwise-correct move?'

The two lens comparison — daily multi-day vs sampled intraday same-day — tells materially different stories, and BOTH have to be taken seriously:

- **Daily lens (n=161 multi-day trades)**: D (thesis-wrong-and-lost) = **50.9%**; B (thesis-right-but-lost) = **18.0%**. Daily D is roughly 2.8× daily B. **Selection dominates on multi-day trades.**
- **Intraday lens (n=100 same-day sampled trades, 10-min bars)**: the largest quadrant is **B' (session-favorable, option lost) at 38.1%**; D' (both wrong) at 26.8%; A' at 27.8%; C' at 7.2%. **Contract/timing failure appears to be the largest single class of loss on same-day trades.**
- The **book is 64.6% same-day trades** by grouped count (73% by lot). So the intraday lens governs the majority of your realized loss dollars. **The evidence points to contract/timing failure being a — arguably the — primary driver on the same-day book, and selection being the primary driver on the multi-day book.**
- **Moneyness overlay**: 36.7% of option trades opened OTM (of which many are OTM_deep). ATM (55.4% of trades) has mean −$5.51/trade; OTM has mean −$10.05/trade; ITM has mean +$13.09. The OTM concentration is exactly where the 'right thesis, wrong contract' failure lives.
- **DTE conditional on FAVORABLE underlying (P2 table)**: on n=71 trades where the underlying moved WITH the trade side at exit close, 8-14 DTE profit-factor was 5.54 and 31+ DTE profit-factor was 12.37 (both n≥22); the 0-1 and 2-7 DTE buckets on the favorable subset were small-N or lost money outright. When the thesis IS right at multi-day resolution, longer DTE captured it and shorter DTE did not.
- **Individual-feature signal (P6)**: `Relative strength on trade side` is the only single feature where TRUE outperformed FALSE (mean +$1.34 vs −$7.25; PF 1.10 vs 0.59). Fresh MACD cross, BB compression, and near-recent-S/R did NOT differentiate favorably on this sample. That's evidence AGAINST 'MACD cross is my edge' on 3 months.

**Overall attribution — honest verdict on this 3-month sample**:
- On MULTI-DAY option trades: **selection is the biggest single contributor to losses** (D >> B on daily bars).
- On SAME-DAY option trades (the majority of the book by count and by dollar loss): **contract-structure / intraday timing failure is the largest single contributor** (B' = 38.1% on the sampled 100). The underlying often went the right way inside the session; the option didn't capitalize.
- **Behavior/risk factors** (same-day at 64.6%, 0-1 DTE at 34.7% of grouped options, OTM concentration, re-entry-within-3-days at 55.7%) amplify both primary modes; they are not a separable third class of loss.
- **Conclusion category**: **multiple factors are material**, and the dominant factor is **book-composition-dependent** — selection on multi-day, contract/timing on same-day. Because most of your book is same-day, contract-structure/execution failure is doing more of the damage than the daily-only analysis alone suggests.
- Reevaluate after (a) a second 3-month window, (b) a fuller intraday sample (200+, not 100), and (c) an intraday-timestamp source (Schwab confirmation emails or the broker's activity API) so real entry/exit times replace the 'entry=open, exit=close' approximation.

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

Given 3 months of realized-lot data, daily bars for 40 tickers, and 10-min intraday bars for 40 tickers over the same window:
- **True intraday entry/exit slippage** — the Schwab CSV has no timestamps. The P3 intraday reconstruction assumes entry ≈ session open and exit ≈ session close. Real entry/exit times could either strengthen or weaken the B' finding materially.
- **Whether PABS setup context predicted these trades** — no historical PABS state is available in this environment. Any 'PABS said X' claim is not defensible from this data.
- **Ticker-level edge** — 3 months is too short to declare any ticker an edge or a curse. All ticker rows are diagnostic; small-N flagged.
- **Regime interaction** — SPY was broadly rising over this window; whether puts underperformed because of a bearish thesis in a rising tape vs. genuinely bad selection is not separable at 3 months.
- **Long-tail tickers (112 of 152, ~24% of grouped trades)** — no bars in cache for these; per-ticker rows exist but no context features / moneyness / intraday for them.
- **Whether the intraday B' finding generalizes** — n=100 sampled trades is a starting point, not an established fact. A larger sample plus a second 3-month window is needed.

## NEXT RESEARCH STEP

Items 2 and 3 from the previous report are now completed (moneyness in P1, intraday sample in P3). Remaining ordered next steps, still no production changes:
1. **Get real intraday timestamps** — pull Schwab's trade-execution history (activity feed / trade confirms), not just the tax lots. Real entry and exit times let the P3 quadrant classify without the entry≈open, exit≈close approximation. This is the single highest-value next step.
2. **Extend the cache to the long-tail 112 tickers.** Uniform coverage removes selection artifacts in the per-ticker table and lets P2/P3 run on the whole book.
3. **Expand the intraday sample from 100 to 300+** with the fuller cache. B' at 38.1% is a big number; confirm it doesn't shrink at scale.
4. **Rerun on the next 3 months of realized data as they land.** All findings above are still provisional at n≈872 grouped trades. Stability across a second window is what matters.
5. **Only after (1)-(4)**: build the setup-tag join (research/context.compute_context_at at entry) so PABS can produce a real 'setup-conditional expectancy' for this trader. Not until.

**Not next steps** (explicitly): no whitelist, no permanent ticker bans, no composite score, no production rule changes, no threshold optimization on this same sample.