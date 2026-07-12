# pabs.trading — NORTH STAR v2
Supersedes v1. v1 got the trader wrong. This is the corrected foundation.
---
## 0. CORRECTIONS TO v1 (state them, don't bury them)
**v1 said: "no intraday data, delete day trades."** WRONG. That was true of Finnhub free,
not of yfinance — which the project already uses and which provides:
- 1h bars: ~730 days of history
- 15m / 5m: ~60 days
- 1m: ~7 days
VERIFY these limits first, then reinstate intraday. Day trades, overnight trades, and
4h/1h confirmation are all feasible. v1 killed them on a false premise.
**v1 said: "checks at lunch, swing only."** WRONG. Four touchpoints:
- **Night before** — prep, place resting orders, build tomorrow's plan
- **Morning (pre/at open)** — act on gaps, confirm or cancel prepped orders
- **Lunch** — manage, add, trim
- **Close** — enter overnight setups, exit day trades, review
This supports day trades, overnight holds, and swings. It does NOT support tick-watching.
Design for DECISION POINTS, not continuous attention.
---
## 1. WHO THIS IS (the real profile)
- **Technical-first**, with fundamentals used when going long / holding.
- **Sector sentiment is the core lens.** Trades sector rotation and SYMPATHY: if batteries
  run, look at lithium and materials next. If rates move, trace what it does downstream.
- **Thrives in trending green markets.** Knows he must adapt for chop and downtrends —
  and knows the adaptation is different, not just smaller.
- **Origin: penny-stock swing options.** Understands optionality and asymmetry natively.
- **Hunts asymmetric long-term winners early**: PLTR @ $6, RKLB @ $3, PL @ $3, NOK @ $5,
  WDC/SNDK @ $30-40, ASTS-type $20 -> $100.
- **Position philosophy — FREE-ROLL:** at +150-200%, sell enough to recover the original
  stake plus some profit; hold the rest as a "free" long-term position. Accumulates a
  portfolio of cost-free holdings over time. THIS IS A CORE FEATURE, NOT A PREFERENCE.
- **Timeframe range:** day trades -> overnight -> swings (< 2 weeks) -> long-term
  investments (only for genuine hidden gems, and only after a free-roll).
---
## 2. TIMEFRAME STACKS (each trade type uses its OWN TF ladder)
Every idea declares its type, and the type determines which timeframes are analyzed,
which confirm, and where the stop lives. NEVER mix them.
| Trade type | Hold | Context TF | Setup TF | Trigger TF | Stop basis | Touchpoint |
|---|---|---|---|---|---|---|
| **Day** | intraday | Daily | 1h | 15m | 15m structure / 1x ATR(1h) | Open + Lunch + Close |
| **Overnight** | 1-3d | Weekly | Daily | 1h/4h | Daily ATR x 0.8 | Close (enter) + Open (exit) |
| **Swing** | 3-14d | Monthly | Weekly | Daily | Daily ATR x 1.5 | Night prep + Close |
| **Position** | 2-8wk | Quarterly | Monthly | Weekly | Weekly ATR x 1.5 | Night prep only |
| **Investment** | months+ | Quarterly | Monthly | Weekly | thesis invalidation, not price | Weekly review |
**RULE: a setup must be confirmed on its Setup TF and not contradicted on its Context TF.**
Trigger TF only times the entry. This is the multi-timeframe coherence gate, done properly
and per trade type — it replaces the broken one that let GOOGL emit a bearish-stance LONG.
**Alignment score** (display on every card):
`MTF: M↑ W↑ D↑ 4h→ 1h↓` — with a verdict: ALIGNED / PULLBACK ENTRY / CONFLICTED.
CONFLICTED never emits. PULLBACK ENTRY (lower TF against, higher TFs with) is the BEST
entry and should be scored as a bonus, not a penalty.
---
## 3. THE SECTOR RELATION ENGINE (the differentiated core — build this first)
This is the user's actual edge and the system has nothing like it. Three layers.
### 3.1 Lead-lag network (measured, not assumed)
Compute a rolling correlation + LEAD-LAG matrix across ~40 sector/theme ETFs:
Core 11 SPDRs + thematic: LIT SMH SOXX XME COPX URA TAN ICLN XOP OIH XBI IBB ITA ARKX
KRE XHB ITB JETS IYT MOO WOOD PAVE BOTZ HACK IPAY XRT SKYY DRIV BATT REMX SIL GDX etc.
For each ETF pair (A, B), over a 6-month rolling window:
- `corr(A, B)` at lag 0
- `xcorr(A, B, lag)` for lag = 1..10 days -> find the lag that MAXIMIZES correlation
- If `xcorr(A -> B, lag=k)` is significantly higher than lag 0, then **A LEADS B by k days**
- Store: `leader, follower, lag_days, strength, n_observations, last_confirmed`
This produces statements like: *"XLE leads XOP by 2 days (r=0.71)"*,
*"BATT leads LIT by 4 days (r=0.63)"*, *"SMH leads SOXX by 1 day (r=0.88)"*.
**The lags are MEASURED from your data, not from my intuition.**
### 3.2 Sympathy propagation (the "batteries -> lithium -> materials" chain)
Maintain a THEME GRAPH — a hand-seeded, machine-validated map of supply-chain relations:
```
battery_demand -> [BATT, LIT] -> [REMX (rare earth), XME (miners), COPX (copper)]
ai_datacenter -> [SMH, SOXX] -> [XLU (power), PAVE (buildout), URA/NLR (nuclear power)]
                             -> [memory: WDC/MU/SNDK]  <- the WDC/SNDK example
rate_cuts -> [XLF, KRE, XHB, ITB, IWM] ; rate_hikes -> inverse + [XLU, XLP defensive]
space_defense -> [ITA, ARKX] -> [RKLB, PL, ASTS type names]
oil_up -> [XLE, XOP, OIH] -> [XME, XLB] ; oil_up -> NEGATIVE for [JETS, XRT]
```
When a NODE fires (an ETF breaks out / turns bullish on the weekly), the engine:
1. Looks up its DOWNSTREAM nodes in the theme graph
2. Checks the measured lead-lag: has the downstream node moved yet?
3. If upstream is running and downstream has NOT -> **SYMPATHY SETUP**, the highest-value
   alert in the system.
4. Ranks the individual NAMES inside the downstream sector by Emerging Strength score
5. Emits the sympathy card.
### 3.3 Bottleneck analysis (where the next theme comes from)
Seed a `bottleneck_watch` config — the constraints that create the next winners:
- power/grid constraint for AI datacenters -> utilities, nuclear, grid equipment, cooling
- memory/HBM supply -> WDC, SNDK, MU
- rare-earth/lithium supply -> REMX, LIT, miners
- launch capacity -> RKLB, space infra
- rate path -> financials/housing/small-caps
For each bottleneck, track: ETF proxies, pure-play names, and a "narrative velocity"
score from the news clustering engine (Addendum 7).
**Honest framing:** bottleneck analysis is a HYPOTHESIS GENERATOR, not a predictor. The
technicals still have to confirm. Narrative without price confirmation is how you buy the top.
---
## 4. THE ASYMMETRY LANE — the "next PLTR at $6" hunter
Shared DNA at the INFLECTION of PLTR@6/RKLB@3/PL@3/NOK@5/WDC-SNDK/ASTS:
1. A long base after a brutal decline (sellers exhausted, chart dead flat for months).
2. A theme about to inflect that the company is a pure-play/key supplier in.
3. First evidence of fundamental turn (rev reacceleration, first profitable quarter, major
   contract, guidance raise) — usually ONE QUARTER before the re-rating.
4. Low/negative sentiment + thin institutional coverage.
5. Cheap absolute price ($3-40).
6. The sector/theme ETF turning up BEFORE the individual name broke out.
### The lane
`ASYMMETRY` — a WATCHLIST lane, not a trade lane. Long horizon. Small size.
Scoring 0-10, requires >= 4 of 6 DNA markers: base_duration_months>=4 & range<40%;
theme_membership accelerating; fundamental_inflection; low_coverage (analysts<=5);
price_accessible $2-50; insider_conviction (cluster buying); sector_early.
Output: a permanent dated ASYMMETRY WATCHLIST (not trades) with thesis + DNA markers +
TRIGGER LEVEL (base high). Entry only on weekly close above base high on volume.
**THE HONEST PART (must be printed on the page):** Most names with this DNA go nowhere.
This lane's edge is NOT hit-rate — it's ASYMMETRY. Size small, spread across many,
free-roll the ones that run. If sized like a swing lane, it will lose money.
---
## 5. FREE-ROLL POSITION MANAGEMENT (a core feature, first-class)
```
Entry: full position size S at price P.
Ladder (configurable): +50% -> trim 15% · +100% -> trim 35% (~50% capital recovered)
  +150% -> trim to FREE-ROLL (proceeds >= original stake + buffer; remainder cost-free)
  Beyond -> free position runs on a WIDE trailing stop (or none for Investment theses).
```
Requirements: `free_roll_status` per position (building|de-risked|FREE|closed); a FREE
POSITIONS dashboard panel; trim levels computed + displayed at entry as resting targets;
`capital_recovered_pct` per position + aggregate; learnings loop tracks upside captured
AFTER the free-roll point (too early vs too late is measurable).
---
## 6. REGIME PLAYBOOKS (regime is a DIFFERENT PLAYBOOK, not a penalty multiplier)
### TRENDING / RISK-ON (home turf)
Lanes: Breakout, Emerging Strength, Compression-fired, Asymmetry entries. Play leaders +
sympathy followers. Full size, hold winners, trail wider. Buy strength/breakouts/retests.
### CHOPPY / RANGE (needs a different brain)
Strongest + weakest sector emphasis (20d RS across 11 SPDRs + themes). Trade top sector's
pullbacks LONG, bottom sector's rallies SHORT. Range/demand levels are everything (mark
demand=range low, supply=range high for SPY/QQQ + sectors; trade from the edges).
Lanes: Oversold Reversal (at demand), Compression, Hidden Value. Half size, faster targets.
KILL the Breakout lane (breakouts fail in chop — verify with shadow data).
Page must say: "CHOP. Strongest: XLE (+4.1%). Weakest: XLK (-3.2%). SPY range 612-628;
demand 612-615. Trade from the edges."
### RISK-OFF / DOWNTREND
Lanes: Hidden Value + Turnaround (accumulate quality, position band), Asymmetry watchlist.
Cash is a position; comfortable saying "few ideas today." Quarter size, tighter time-stops.
### UNKNOWN (degraded data)
Promote NOTHING. Say so plainly. Never fabricate a regime from missing data.
---
## 7. THE DAILY RHYTHM (four touchpoints, FOUR VIEWS not one dashboard)
- **NIGHT BEFORE** (main prep): tomorrow's plan, regime, sector leaders/laggards + sympathy;
  orders to place (setups w/ limit/stop/target + trim ladder); watchlist; open positions.
- **MORNING (open)**: gaps, day-trade candidates (1h/15m structure), confirm/cancel resting orders.
- **LUNCH**: position check (trim levels/invalidation), day-trade management, intraday rotation.
- **CLOSE**: enter overnight setups, exit day trades, log the day for the learnings loop.
Each view answers "what do I do RIGHT NOW" for that moment.
---
## 8. BUILD ORDER
1. Verify yfinance intraday. 2. Fix bugs (R:R floor, stance/direction, Mag7 no-plan,
composite ceiling). 3. TF stacks + alignment score. 4. Sector Relation Engine (lead-lag ->
sympathy -> bottleneck) — THE differentiator, before more lanes. 5. Regime playbooks
(chop strongest/weakest + range-demand levels). 6. Shadow tracking. 7. Six thesis lanes
(Turnaround · Oversold Reversal · Hidden Value · Breakout · Compression · Emerging
Strength) + ASYMMETRY watchlist. 8. Free-roll + FREE POSITIONS panel. 9. Four daily views.
10. Learning loop (monthly, versioned weights, lane x regime table).
