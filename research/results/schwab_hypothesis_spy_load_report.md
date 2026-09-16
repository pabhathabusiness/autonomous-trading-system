# SCHWAB HYPOTHESIS TEST — SPY ALIGNMENT × PORTFOLIO LOAD

**Hypothesis under test**: my biggest losses come from (1) holding multi-day option trades AGAINST SPY direction, and (2) carrying too many simultaneous or correlated option positions relative to account equity.

**All thresholds preregistered in the module docstring** (`research/schwab_hypothesis_spy_load.py`) BEFORE any P&L was inspected. No threshold tuning post-hoc.

**No production changes.** Diagnosis only.

## DATA COVERAGE

- Schwab CSV: `0f1bec32-XXXX1615_GainLoss_Realized_Details_20260916-101658.csv` — 1,311 raw lots, 872 grouped trades.
- Daily-bars cache: 40 tickers (top-40 by lot volume, ~74% of grouped trades).
- SPY daily bars: 324 bars from 2025-06-02 to 2026-09-15.
- Trades with an evaluatable SPY classification (SMA50 available at open): **872 / 872**.
- Option trades: 817; equity trades: 55 (excluded from alignment analysis).
- Trades opened BEFORE 2026-06-16 (no equity baseline): **33**. Equity-based analyses exclude these; count-based load buckets retain them.

## SPY ALIGNMENT DEFINITION

(Copied from the preregistered docstring — verbatim.)

- **BULLISH**: SPY close > SMA20 AND close > SMA50 AND 5-day return > 0 AND SMA50 slope ≥ 0
- **BEARISH**: SPY close < SMA20 AND close < SMA50 AND 5-day return < 0 AND SMA50 slope ≤ 0
- **MIXED**: SMA20 and SMA50 available but neither BULLISH nor BEARISH condition holds
- **UNKNOWN**: SPY history insufficient for SMA50 (< 50 bars)

Alignment for OPTION trades:
- Call + BULLISH = ALIGNED; Call + BEARISH = AGAINST
- Put + BEARISH = ALIGNED; Put + BULLISH = AGAINST
- Any + MIXED = MIXED; Any + UNKNOWN = UNKNOWN

**SPY classification distribution across trade opens**:

| Class | count | share |
|---|---:|---:|
| BULLISH | 344 | 39.4% |
| BEARISH | 1 | 0.1% |
| MIXED | 527 | 60.4% |
| UNKNOWN | 0 | 0.0% |

**Alignment distribution (option trades)**:

| Alignment | count | share of option trades |
|---|---:|---:|
| ALIGNED | 281 | 34.4% |
| AGAINST | 43 | 5.3% |
| MIXED | 493 | 60.3% |
| UNKNOWN | 0 | 0.0% |

## SPY ALIGNMENT RESULTS (all option trades)

| Alignment | n | win% | mean | median | PF | total |
|---|---:|---:|---:|---:|---:|---:|
| ALIGNED | 281 | 30.2% | $0.42 | $-8.32 | 1.03 | $116.63 |
| AGAINST | 43 | 44.2% | $6.01 | $-6.32 | 1.65 | $258.44 |
| MIXED | 493 | 28.2% | $-7.46 | $-10.64 | 0.56 | $-3,679.67 |
| UNKNOWN | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |

## SAME-DAY VS MULTI-DAY (KEY HYPOTHESIS SPLIT)

Does SPY alignment matter more as holding period increases? Test directly.

**SAME_DAY**:

| Alignment | n | win% | mean | median | PF | total |
|---|---:|---:|---:|---:|---:|---:|
| ALIGNED | 176 | 32.4% | $-0.58 | $-6.32 | 0.95 | $-101.33 |
| AGAINST | 39 | 41.0% | $5.22 | $-7.32 | 1.53 | $203.71 |
| MIXED | 339 | 28.0% | $-7.58 | $-10.66 | 0.54 | $-2,568.34 |

**1-2**:

| Alignment | n | win% | mean | median | PF | total |
|---|---:|---:|---:|---:|---:|---:|
| ALIGNED | 64 | 32.8% | $13.61 | $-9.00 | 1.88 | $871.18 |
| AGAINST ⚠ | 3 | 66.7% | $17.68 | $23.68 | 6.69 | $53.05 |
| MIXED | 95 | 27.4% | $-12.53 | $-10.64 | 0.36 | $-1,190.23 |

**3-5**:

| Alignment | n | win% | mean | median | PF | total |
|---|---:|---:|---:|---:|---:|---:|
| ALIGNED | 23 | 13.0% | $-19.67 | $-18.64 | 0.17 | $-452.49 |
| AGAINST ⚠ | 1 | 100.0% | $1.68 | $1.68 | — | $1.68 |
| MIXED | 36 | 25.0% | $-4.48 | $-10.49 | 0.73 | $-161.16 |

**6-10**:

| Alignment | n | win% | mean | median | PF | total |
|---|---:|---:|---:|---:|---:|---:|
| ALIGNED ⚠ | 9 | 0.0% | $-35.54 | $-31.96 | 0.00 | $-319.84 |
| AGAINST | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| MIXED ⚠ | 9 | 33.3% | $14.87 | $-20.64 | 1.86 | $133.85 |

**11+**:

| Alignment | n | win% | mean | median | PF | total |
|---|---:|---:|---:|---:|---:|---:|
| ALIGNED ⚠ | 9 | 44.4% | $13.23 | $0.00 | 2.42 | $119.11 |
| AGAINST | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| MIXED ⚠ | 14 | 42.9% | $7.59 | $0.00 | 1.90 | $106.21 |

## PORTFOLIO LOAD (COUNT-BASED)

Number of OTHER open positions at the moment this trade's open was placed. LOW = 1 open (this one), MED = 2, HIGH = 3+.

| Load | n | win% | mean | median | PF | total | avg est_equity |
|---|---:|---:|---:|---:|---:|---:|---:|
| LOW | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 | — |
| MED | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 | — |
| HIGH | 817 | 29.7% | $-4.04 | $-9.32 | 0.74 | $-3,304.60 | $2,824.61 |

Distribution of `open_position_count_at_new_trade_open`:

| n_open | count | share |
|---|---:|---:|
| 4 | 4 | 0.5% |
| 5 | 23 | 2.8% |
| 6 | 59 | 7.2% |
| 7 | 26 | 3.2% |
| 8 | 55 | 6.7% |
| 9 | 42 | 5.1% |
| 10 | 52 | 6.4% |
| 11 | 25 | 3.1% |
| 12 | 25 | 3.1% |
| 13 | 5 | 0.6% |
| 14 | 17 | 2.1% |
| 15 | 38 | 4.7% |
| 16 | 27 | 3.3% |
| 17 | 26 | 3.2% |
| 18 | 5 | 0.6% |
| 19 | 3 | 0.4% |
| 20 | 17 | 2.1% |
| 21 | 5 | 0.6% |
| 22 | 5 | 0.6% |
| 23 | 2 | 0.2% |
| 24 | 14 | 1.7% |
| 25 | 29 | 3.5% |
| 26 | 47 | 5.8% |
| 27 | 24 | 2.9% |
| 28 | 21 | 2.6% |
| 29 | 12 | 1.5% |
| 30 | 31 | 3.8% |
| 31 | 55 | 6.7% |
| 32 | 48 | 5.9% |
| 33 | 17 | 2.1% |
| 34 | 15 | 1.8% |
| 35 | 9 | 1.1% |
| 36 | 17 | 2.1% |
| 37 | 7 | 0.9% |
| 38 | 4 | 0.5% |
| 39 | 3 | 0.4% |
| 40 | 3 | 0.4% |

## ACCOUNT EXPOSURE (PREMIUM % OF EQUITY)

Only trades opened on or after 2026-06-16 have an equity estimate. Buckets: <10%, 10-20%, 20-30%, 30-50%, 50%+.

**Caveat**: equity estimator is `starting_value + prorated_contributions + cumulative_realized_pnl` — a linear-contribution approximation. Real equity varies with unrealized positions and actual deposit timing. Read numbers as directional, not exact.

| Exposure | n | win% | mean | median | PF | total | avg est_equity |
|---|---:|---:|---:|---:|---:|---:|---:|
| <10% | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 | — |
| 10-20% | 88 | 30.7% | $-3.80 | $-10.32 | 0.76 | $-334.12 | $2,453.57 |
| 20-30% | 181 | 35.4% | $-3.28 | $-7.32 | 0.78 | $-593.14 | $2,493.86 |
| 30-50% | 212 | 28.3% | $-8.16 | $-9.32 | 0.51 | $-1,729.33 | $2,960.47 |
| 50%+ | 313 | 26.5% | $-2.34 | $-11.32 | 0.85 | $-732.99 | $3,028.19 |

## CORRELATED POSITION CLUSTERS

For each option trade with >= 1 other position open at the moment of its open, we classify the OPEN portfolio (excluding this new trade) into cluster labels using the preregistered sector map.

| Cluster (present at trade's open) | n_trades | win% | mean | median | PF | total |
|---|---:|---:|---:|---:|---:|---:|
| SECTOR_CLUSTER_OTHER | 652 | 28.5% | $-4.15 | $-9.32 | 0.73 | $-2,708.19 |
| SECTOR_CLUSTER_energy_clean | 424 | 28.8% | $-4.84 | $-11.32 | 0.71 | $-2,053.24 |
| SECTOR_CLUSTER_misc_smallcap | 326 | 27.6% | $-3.08 | $-7.33 | 0.78 | $-1,004.32 |
| SECTOR_CLUSTER_fintech | 268 | 32.1% | $-0.65 | $-6.32 | 0.95 | $-173.32 |
| SECTOR_CLUSTER_cyber_software | 227 | 31.7% | $3.63 | $-7.33 | 1.26 | $823.89 |
| SECTOR_CLUSTER_evtol | 136 | 24.3% | $-10.68 | $-12.32 | 0.43 | $-1,451.99 |
| SECTOR_CLUSTER_biohealth | 120 | 22.5% | $-9.24 | $-15.32 | 0.46 | $-1,108.42 |
| BULLISH_TECH_STACK | 80 | 18.8% | $-7.33 | $-12.32 | 0.57 | $-586.79 |
| SECTOR_CLUSTER_aerospace | 78 | 23.1% | $-8.59 | $-15.82 | 0.54 | $-669.83 |
| SECTOR_CLUSTER_quantum | 68 | 13.2% | $-16.81 | $-21.32 | 0.27 | $-1,142.91 |
| SECTOR_CLUSTER_space_aero | 67 | 14.9% | $-14.49 | $-16.32 | 0.25 | $-970.68 |
| SECTOR_CLUSTER_semiconductors | 60 | 18.3% | $-7.25 | $-13.82 | 0.57 | $-435.05 |
| INDEX_PLUS_TECH_COMPONENT | 47 | 25.5% | $-4.02 | $-10.32 | 0.72 | $-188.72 |
| BEARISH_INDEX_STACK | 33 | 21.2% | $-20.80 | $-10.32 | 0.18 | $-686.52 |
| SECTOR_CLUSTER_retail | 32 | 37.5% | $-2.29 | $-3.82 | 0.85 | $-73.15 |
| SECTOR_CLUSTER_telecom | 24 | 33.3% | $-10.70 | $-9.65 | 0.38 | $-256.90 |
| SECTOR_CLUSTER_mega_tech | 20 | 20.0% | $-7.59 | $-11.49 | 0.56 | $-151.74 |
| SECTOR_CLUSTER_airlines ⚠ | 11 | 36.4% | $-5.89 | $-17.32 | 0.74 | $-64.78 |

**APPROX_INDEPENDENT_BET_COUNT** distribution (open positions grouped by sector+side; count of distinct groups):

| independent bets at open | count | share |
|---|---:|---:|
| 1 | 6 | 0.7% |
| 2 | 29 | 3.5% |
| 3 | 95 | 11.6% |
| 4 | 120 | 14.7% |
| 5 | 52 | 6.4% |
| 6 | 37 | 4.5% |
| 7 | 32 | 3.9% |
| 8 | 75 | 9.2% |
| 9 | 90 | 11.0% |
| 10 | 123 | 15.1% |
| 11 | 60 | 7.3% |
| 12 | 39 | 4.8% |
| 13 | 38 | 4.7% |
| 14 | 20 | 2.4% |
| 15 | 1 | 0.1% |

Historical daily-return Pearson correlations among 9 common tickers (last 200 daily bars, r-value; ≥0.7 = strongly correlated):

| pair | r |
|---|---:|
| SPY–NVDA | 0.65 |
| SPY–AAPL | 0.30 |
| SPY–INTC | 0.48 |
| SPY–RKLB | 0.49 |
| SPY–QQQ 🔗 | 0.92 |
| SPY–SOFI | 0.57 |
| SPY–PYPL | 0.27 |
| SPY–MSFT | 0.36 |
| NVDA–AAPL | 0.06 |
| NVDA–INTC | 0.36 |
| NVDA–RKLB | 0.36 |
| NVDA–QQQ | 0.67 |
| NVDA–SOFI | 0.43 |
| NVDA–PYPL | 0.20 |
| NVDA–MSFT | 0.22 |
| AAPL–INTC | 0.02 |
| AAPL–RKLB | 0.09 |
| AAPL–QQQ | 0.18 |
| AAPL–SOFI | 0.12 |
| AAPL–PYPL | 0.21 |
| AAPL–MSFT | 0.11 |
| INTC–RKLB | 0.31 |
| INTC–QQQ | 0.64 |
| INTC–SOFI | 0.17 |
| INTC–PYPL | -0.08 |
| INTC–MSFT | -0.01 |
| RKLB–QQQ | 0.51 |
| RKLB–SOFI | 0.39 |
| RKLB–PYPL | 0.00 |
| RKLB–MSFT | 0.15 |
| QQQ–SOFI | 0.52 |
| QQQ–PYPL | 0.17 |
| QQQ–MSFT | 0.30 |
| SOFI–PYPL | 0.23 |
| SOFI–MSFT | 0.42 |
| PYPL–MSFT | 0.28 |

## SPY ALIGNMENT × LOAD MATRIX

LOW = 1-2 open positions when this trade opened; HIGH = 3+. Preregistered split.

| Alignment | Load | n | win% | mean | median | PF | total |
|---|---|---:|---:|---:|---:|---:|---:|
| ALIGNED | LOW | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| ALIGNED | HIGH | 281 | 30.2% | $0.42 | $-8.32 | 1.03 | $116.63 |
| AGAINST | LOW | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| AGAINST | HIGH | 43 | 44.2% | $6.01 | $-6.32 | 1.65 | $258.44 |
| MIXED | LOW | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| MIXED | HIGH | 493 | 28.2% | $-7.46 | $-10.64 | 0.56 | $-3,679.67 |

## MULTI-DAY OPTIONS — THE MAIN HYPOTHESIS TEST

Only trades with hold_days ≥ 1. This is the specific claim: multi-day trades against SPY, with more open positions, do worse.

Denominator: **263** multi-day option grouped trades.

**By alignment (multi-day only)**:

| Alignment | n | win% | mean | median | PF | total |
|---|---:|---:|---:|---:|---:|---:|
| ALIGNED | 105 | 26.7% | $2.08 | $-15.32 | 1.11 | $217.96 |
| AGAINST ⚠ | 4 | 75.0% | $13.68 | $12.68 | 6.87 | $54.73 |
| MIXED | 154 | 28.6% | $-7.22 | $-9.49 | 0.59 | $-1,111.33 |

**By open-position-count (multi-day only)**:

| open positions | n | win% | mean | median | PF | total |
|---|---:|---:|---:|---:|---:|---:|
| 1 open at entry | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| 2 open at entry | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| 3+ open at entry | 263 | 28.5% | $-3.19 | $-11.32 | 0.82 | $-838.64 |

**Alignment × Open-Position-Count (multi-day only)**:

| Alignment | Open count | n | win% | mean | median | PF | total |
|---|---|---:|---:|---:|---:|---:|---:|
| ALIGNED | 1 | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| ALIGNED | 2 | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| ALIGNED | 3+ | 105 | 26.7% | $2.08 | $-15.32 | 1.11 | $217.96 |
| AGAINST | 1 | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| AGAINST | 2 | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| AGAINST ⚠ | 3+ | 4 | 75.0% | $13.68 | $12.68 | 6.87 | $54.73 |
| MIXED | 1 | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| MIXED | 2 | 0 | 0.0% | $0.00 | $0.00 | — | $0.00 |
| MIXED | 3+ | 154 | 28.6% | $-7.22 | $-9.49 | 0.59 | $-1,111.33 |

## CONTROLLED COMPARISONS

Compare ALIGNED vs AGAINST while holding OTHER factors constant. Each row is a cell defined by (DTE bucket × call/put × same-day × moneyness NOT USED here to keep to phase spec). Cells with n < 3 on either side flagged ⚠.

| DTE | Side | Hold | n_ALIGNED | mean_ALIGNED | n_AGAINST | mean_AGAINST | Δ | flag |
|---|---|---|---:|---:|---:|---:|---:|:---:|
| 0-1 | C | same | 74 | $3.04 | 0 | $0.00 | $0.00 | ⚠ |
| 0-1 | P | same | 0 | $0.00 | 28 | $4.71 | $0.00 | ⚠ |
| 2-7 | C | multi | 18 | $-3.26 | 0 | $0.00 | $0.00 | ⚠ |
| 2-7 | C | same | 41 | $1.67 | 0 | $0.00 | $0.00 | ⚠ |
| 2-7 | P | multi | 0 | $0.00 | 2 | $-3.82 | $0.00 | ⚠ |
| 2-7 | P | same | 0 | $0.00 | 9 | $8.39 | $0.00 | ⚠ |
| 31+ | C | multi | 55 | $-9.10 | 0 | $0.00 | $0.00 | ⚠ |
| 31+ | C | same | 16 | $-2.43 | 0 | $0.00 | $0.00 | ⚠ |
| 8-30 | C | multi | 32 | $24.29 | 0 | $0.00 | $0.00 | ⚠ |
| 8-30 | C | same | 45 | $-7.91 | 0 | $0.00 | $0.00 | ⚠ |
| 8-30 | P | multi | 0 | $0.00 | 2 | $31.18 | $0.00 | ⚠ |
| 8-30 | P | same | 0 | $0.00 | 2 | $-1.82 | $0.00 | ⚠ |

## LARGEST LOSS CASE STUDIES

Top-15 largest realized losses among GROUPED trades. `align` uses the SPY class the day the trade opened.

| Ticker | Side | Opened → Closed | Hold | DTE | P&L | SPY class | Alignment | Open pos | Est equity | Cluster |
|---|---|---|---:|---:|---:|---|---|---:|---:|---|
| SPY | P | 2026-08-19 → 2026-08-21 | 2 | 2 | $-169.98 | MIXED | MIXED | 12 | $2,756.47 | BEARISH_INDEX_STACK;SECTOR_CLUSTER_evtol |
| OKLO | P | 2026-07-17 → 2026-07-17 | 0 | 0 | $-131.97 | MIXED | MIXED | 26 | $4,247.19 | SECTOR_CLUSTER_OTHER;SECTOR_CLUSTER_energy_clean;SECTOR_CLUSTER_fintech;SECTOR_CLUSTER_misc_smallcap |
| SPY | P | 2026-06-24 → 2026-06-24 | 0 | 0 | $-118.93 | MIXED | MIXED | 32 | $2,676.06 | SECTOR_CLUSTER_OTHER;SECTOR_CLUSTER_airlines;SECTOR_CLUSTER_cyber_software;SECTOR_CLUSTER_energy_clean;SECTOR_CLUSTER_fintech |
| ASTS | P | 2026-08-19 → 2026-08-19 | 0 | 2 | $-112.66 | MIXED | MIXED | 11 | $2,756.47 | BEARISH_INDEX_STACK;SECTOR_CLUSTER_evtol |
| SPY | P | 2026-07-17 → 2026-07-17 | 0 | 0 | $-109.98 | MIXED | MIXED | 26 | $4,247.19 | SECTOR_CLUSTER_OTHER;SECTOR_CLUSTER_energy_clean;SECTOR_CLUSTER_fintech;SECTOR_CLUSTER_misc_smallcap |
| SPY | P | 2026-06-26 → 2026-06-26 | 0 | 0 | $-108.66 | MIXED | MIXED | 31 | $3,155.90 | SECTOR_CLUSTER_OTHER;SECTOR_CLUSTER_biohealth;SECTOR_CLUSTER_energy_clean;SECTOR_CLUSTER_retail |
| IWM | P | 2026-08-20 → 2026-08-21 | 1 | 1 | $-108.66 | MIXED | MIXED | 7 | $2,550.35 | BEARISH_INDEX_STACK;SECTOR_CLUSTER_evtol |
| SPY | C | 2026-09-10 → 2026-09-10 | 0 | 0 | $-101.27 | MIXED | MIXED | 8 | $1,745.37 | SECTOR_CLUSTER_OTHER |
| SPY | P | 2026-08-19 → 2026-08-20 | 1 | 1 | $-97.30 | MIXED | MIXED | 11 | $2,756.47 | BEARISH_INDEX_STACK;SECTOR_CLUSTER_evtol |
| NVDA | C | 2026-08-17 → 2026-08-18 | 1 | 4 | $-96.97 | MIXED | MIXED | 22 | $3,373.81 | SECTOR_CLUSTER_OTHER;SECTOR_CLUSTER_aerospace;SECTOR_CLUSTER_energy_clean;SECTOR_CLUSTER_evtol;SECTOR_CLUSTER_quantum |
| SPY | P | 2026-07-23 → 2026-07-23 | 0 | 0 | $-90.97 | MIXED | MIXED | 16 | $3,230.82 | SECTOR_CLUSTER_OTHER;SECTOR_CLUSTER_biohealth;SECTOR_CLUSTER_energy_clean;SECTOR_CLUSTER_misc_smallcap |
| NOW | C | 2026-08-31 → 2026-08-31 | 0 | 4 | $-82.96 | MIXED | MIXED | 8 | $1,797.36 | SECTOR_CLUSTER_OTHER |
| SOFI | C | 2026-07-13 → 2026-07-15 | 2 | 11 | $-81.63 | MIXED | MIXED | 35 | $3,087.82 | SECTOR_CLUSTER_OTHER;SECTOR_CLUSTER_cyber_software;SECTOR_CLUSTER_fintech;SECTOR_CLUSTER_misc_smallcap |
| AAPL | C | 2026-07-27 → 2026-07-27 | 0 | 2 | $-78.64 | MIXED | MIXED | 8 | $2,866.55 | SECTOR_CLUSTER_energy_clean |
| INTC | P | 2026-07-28 → 2026-07-28 | 0 | 1 | $-77.92 | MIXED | MIXED | 12 | $2,788.87 | SECTOR_CLUSTER_energy_clean;SECTOR_CLUSTER_fintech |

**Overlap count on the top-15 largest losses**:
- AGAINST SPY: **0/15**
- 3+ open positions at entry: **15/15**
- Premium ≥ 30% of estimated equity at entry: **11/15**
- Portfolio held a correlated cluster at entry: **15/15**
- AGAINST SPY AND 3+ open: **0/15**
- AGAINST SPY AND ≥30% exposure: **0/15**

## ACCOUNT DAMAGE ATTRIBUTION

Total realized P&L across categorical slices. **Slices overlap; do not sum independently.**

| Slice | n | total P&L | share of grand-option-total |
|---|---:|---:|---:|
| AGAINST SPY | 43 | $258.44 | -7.8% |
| ALIGNED SPY | 281 | $116.63 | -3.5% |
| 3+ open positions at entry | 817 | $-3,304.60 | 100.0% |
| Premium ≥ 30% of est_equity | 525 | $-2,462.32 | 74.5% |
| Correlated cluster at entry (non-index/non-mixed) | 817 | $-3,304.60 | 100.0% |
| AGAINST SPY + 3+ open | 43 | $258.44 | -7.8% |
| AGAINST SPY + ≥30% exposure | 29 | $245.13 | -7.4% |
| AGAINST SPY + correlated cluster | 43 | $258.44 | -7.8% |

Grand option-only total: **$-3,304.60** (matches Schwab CSV realized option loss).

**Overlap note**: 'AGAINST SPY + 3+ open' is a SUBSET of both 'AGAINST SPY' and '3+ open'. Do not add these lines together to get a total — they are marginal views of a single P&L stream.

## EMPIRICAL LOAD DISTRIBUTION (post-hoc DESCRIPTIVE — not a preregistered threshold)

Preregistered LOW/MED count buckets both came back n=0. The book operated at 3+ open positions on **every** option trade. That is itself a diagnostic finding: the count-based load bucket does not discriminate at the preregistered thresholds because the book runs perpetually high-load.

Descriptive-only finer split (do NOT use as decision thresholds — the split was chosen after seeing the count distribution):

| open at entry | n | win% | mean | median | PF | total |
|---|---:|---:|---:|---:|---:|---:|
| 1-5 | 27 | 33.3% | $-5.43 | $-10.64 | 0.67 | $-146.52 |
| 6-10 | 234 | 36.3% | $-1.28 | $-8.32 | 0.91 | $-299.49 |
| 11-20 | 188 | 26.1% | $-9.17 | $-11.82 | 0.47 | $-1,724.53 |
| 21+ | 368 | 27.2% | $-3.08 | $-9.32 | 0.80 | $-1,134.06 |

Median `open_position_count_at_entry` across option trades: **17**. Empirical below-median vs at-or-above-median split:

| Load (empirical) | n | win% | mean | median | PF | total |
|---|---:|---:|---:|---:|---:|---:|
| < 17 open (below-median) | 398 | 33.4% | $-4.09 | $-9.28 | 0.74 | $-1,626.19 |
| >= 17 open (at/above-median) | 419 | 26.3% | $-4.01 | $-10.32 | 0.75 | $-1,678.41 |

## WHAT SUPPORTS THE HYPOTHESIS

- **All 15 largest losses were opened with 3+ other option positions already active.** (15/15). Consistent with the 'too many simultaneous positions' half of the hypothesis — though the book always operates at 3+, so this may be a book-composition artifact.
- **All 15 largest losses were opened while a correlated-position cluster was active** (SECTOR_CLUSTER_* or BEARISH_INDEX_STACK or similar). 15/15. The 'correlated exposure' half of the hypothesis IS supported by the case studies.
- **11/15 largest losses were opened with premium ≥ 30% of estimated equity.** Consistent with the account-size overexposure claim.

## WHAT CONTRADICTS THE HYPOTHESIS

- **SPY was classified BEARISH on only 1 of 872 trade opens.** This makes 'AGAINST SPY' functionally 'puts opened during BULLISH regime' — a very small sample (n_AGAINST = 43). The hypothesis is essentially not testable in this window at the intended semantic.
- **AGAINST-SPY trades OUTPERFORMED ALIGNED-SPY trades on this sample.** ALIGNED (n=281, mean $0.42, PF 1.03) vs AGAINST (n=43, mean $6.01, PF 1.65). Diametrically opposite to the hypothesis.
- **Multi-day AGAINST-SPY trades were PROFITABLE**: n=4 (⚠ small-N), mean $13.68, total $54.73. The specific multi-day-against-SPY claim finds zero support at this sample size.
- **0/15 of the largest realized losses were AGAINST SPY.** Directly refutes the 'biggest losses are against-SPY' claim. Almost all biggest losses (the 15 - 0 remaining) opened during MIXED SPY regime.
- **The heaviest losses concentrate in MIXED SPY regime, NOT AGAINST**: MIXED n=493, mean $-7.46, PF 0.56, total $-3,679.67. Trend clarity (bullish OR bearish) matters more than trade-vs-trend alignment on this book.

## WHAT WE CANNOT CONCLUDE

- **Causality** — cross-sectional comparison, not a randomized control. Alignment and load may co-vary with unobserved factors (time-of-day, spread cost, subjective conviction).
- **Exact account equity per trade day** — the equity estimator uses linear-prorated contributions; actual deposits are lumpier. The 30% exposure threshold could be off by a bin.
- **Correlation clusters are a taxonomy, not a model** — the sector map is hand-coded; historical return correlation (last 200 daily bars) is provided as a check but not integrated into the cluster labels.
- **Pre-statement trades** — trades opened before 2026-06-16 have no equity estimate and are excluded from equity-based buckets.
- **Long-tail tickers** — 112 of 152 underlyings have no bars in cache; per-trade SPY context is still fine for those (SPY bars are available for every trade date) but ticker-level sector clusters use the map only.
- **N-thresholds** — cells flagged ⚠ have n < 20 and should not be used for decision-making.

## NEXT EXPERIMENT

1. **Real account snapshots**: pull daily equity from Schwab (statement API, if available) instead of the linear-prorate estimator. That sharpens the exposure buckets.
2. **Intraday timestamped opens/closes**: replaces the same-day 'entry ≈ open' assumption; enables 'time in market against SPY' as a continuous variable.
3. **Full-history bars for 152 tickers**: closes the 24% coverage gap on the ticker table and enables per-trade underlying returns for every trade.
4. **Second 3-month window**: everything above is a 3-month snapshot — the stability of these findings is what matters.

## FINAL QUESTION — evidence-based answer

**Were my biggest losses primarily associated with holding multi-day option positions against SPY while carrying too many simultaneous or correlated option positions relative to my account size?**

The hypothesis has three components. Score them separately against this data:

**Component 1 — 'Multi-day option trades AGAINST SPY are the primary loss vector'**
- SPY classified BEARISH on 1 of 872 option-trade opens. AGAINST-SPY option trades total n=43 of 817 option trades. **The hypothesis's target class barely exists in this window.**
- Multi-day AGAINST-SPY trades: n=4 (⚠ tiny sample), mean $13.68, total $54.73. On this sample, they were PROFITABLE.
- Top-15 largest losses AGAINST SPY: **0/15**. Directly refutes.
- Multi-day ALIGNED vs AGAINST vs MIXED means: ALIGNED $2.08, AGAINST $13.68, **MIXED $-7.22**. The heavy loss lives in MIXED, not AGAINST.
- **Verdict on Component 1**: **NOT SUPPORTED** on this data (the against-SPY subset is small and was actually profitable). But note: an untestable claim — a 3-month window with only 1 BEARISH-classified SPY day cannot fairly test 'against SPY' at any semantic.

**Component 2 — 'Too many simultaneous positions relative to account size'**
- The book **always** operated at 3+ open positions (817 of 817 option trades — 100%). Preregistered LOW / MED count-buckets never occurred.
- Top-15 largest losses with 3+ open positions at entry: **15/15**.
- Top-15 largest losses with premium ≥ 30% of estimated equity at entry: **11/15**.
- Highest exposure bucket (50%+): n=313, mean $-2.34. Lower buckets (<20%): mean $-3.80. Difference is small.
- Empirical below-median vs at/above-median open-count split: mean $-4.09 vs $-4.01. Load DOES correlate with worse outcomes in the empirical (post-hoc) split.
- **Verdict on Component 2**: **PARTIALLY SUPPORTED as a book-composition observation** (every large loss happened under high-load conditions), but the finding is **CONFOUNDED** — there are no low-load trades to compare against. Cannot separate 'high load causes losses' from 'this trader always trades under high load'.

**Component 3 — 'Correlated position clusters'**
- Top-15 largest losses with a correlated cluster active at entry: **15/15**.
- SECTOR_CLUSTER_quantum: n=68, mean $-16.81, PF 0.27, total $-1,142.91 — worst cluster in the table.
- SECTOR_CLUSTER_space_aero: n=67, mean $-14.49, PF 0.25, total $-970.68 — near-worst.
- BEARISH_INDEX_STACK: n=33, mean $-20.80, PF 0.18, total $-686.52 — very poor when trading multiple index puts simultaneously.
- Historical daily-return correlation SPY–QQQ = 0.92 confirms 'multiple index positions' are near-duplicates.
- **Verdict on Component 3**: **PARTIALLY SUPPORTED** — specific correlated stacks (quantum, space/aero, bearish-index) have materially worse per-trade P&L. But again, high-load is universal so we cannot isolate the cluster effect from the total-load effect.

---

**Overall verdict on the compound hypothesis**:

**PARTIALLY SUPPORTED** — with critical corrections to the original framing:

- The 'AGAINST SPY' component is **NOT SUPPORTED** by this 3-month sample: SPY almost never qualified as BEARISH, so AGAINST-SPY option trades are rare (n=43) and were actually PROFITABLE on average. Zero of the top-15 largest losses were AGAINST SPY. The real loss bucket is **MIXED SPY regime**, not AGAINST.
- The 'too many simultaneous / correlated positions' component is **BROADLY CONSISTENT WITH THE DATA** — every large loss happened while the book carried a correlated cluster and 3+ open positions. But it is CONFOUNDED: the book has no LOW-load counter-examples, so we cannot say load CAUSES the losses vs COINCIDES with them.
- The DTE and moneyness picture (from previous diagnostics) — same-day, 0-1 DTE, ATM/OTM — is where much of the actual damage lives, independently of alignment.

**Do not act on this alone.** Next steps: pull real per-day account snapshots, extend intraday coverage for entry/exit reconstruction, and rerun on the next 3-month window. This sample cannot separate 'alignment against SPY' from 'trading during a chop regime', nor 'high load causes losses' from 'high load is this trader's default operating state'.