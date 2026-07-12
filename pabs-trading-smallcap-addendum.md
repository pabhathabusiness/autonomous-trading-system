# Addendum 2 — Sub-$5 Momentum & News Page ("Small Caps" lane)

Extends pabs-trading-final-spec.md. HARD RULE: this is a QUARANTINED lane.
Separate page, separate `book` tag on every row (`book='smallcap'` vs `book='swing'`),
separate stat cards, separate learnings file (`learnings_smallcap.json`). Nothing here
ever enters the main book's expectancy, grades, or scanner rules. Paper-only until its
own stats earn otherwise (n ≥ 30 closed with positive expectancy).

## Universe definition (new table `smallcap_universe`, refreshed daily premarket)
- price: $0.50 – $5.00  (keep the existing min_price_floor: exclude < $1.00 if spread > 50bps)
- float tiers: `runner < 20M` · `low 20–30M` · `standard 30M–100M`
  The `runner` tier (< 20M float) gets its OWN MINI-TAB at the top of the page —
  "Runners" — because these are the names that move 50-300% on catalyst days. Mini-tab
  shows only runner-tier triggers, sorted by rel_vol desc, with float shown in M on
  every card. The 20-30M tier appears in the main list with a `low float` badge.
- avg daily $ volume ≥ $500k trailing 20d (below this, fills are fiction even on paper)
- exchange-listed only (NASDAQ/NYSE/AMEX) — no OTC
- exclude: biotech with no catalyst date? No — include, but tag `sector_name` so it's filterable
- DILUTION FLAG (critical): daily filings check per symbol — active S-3/S-1 shelf,
  recent 424B pricing, ATM agreement, or share count growth > 20% in 6 months →
  `dilution_risk = true`. This is a display flag AND a verdict input.
- DEATHWATCH EXCLUSION (hard filter — these never appear in any scan, ever):
  a. reverse split within 18 months (split ratio < 1 in split history) — serial
     compliance-splitters are the #1 bankruptcy-track tell
  b. two or more reverse splits in 5 years → permanent exclusion
  c. "going concern" language in the latest 10-K/10-Q (Finnhub filings text search)
  d. share count growth > 100% in 12 months (the dilution treadmill)
  e. price < $1 for > 20 consecutive trading days (delisting-notice territory)
  Store excluded names in `smallcap_deathwatch` with the triggering reason and date —
  render as a collapsible "Excluded (deathwatch)" list at the page bottom with the
  reason per name, so exclusions are auditable, not silent. Names can exit deathwatch
  only by aging out of the criteria, never manually.

## Data sources (be explicit about gaps — do not fake fields)
| Field | Source | Note |
|---|---|---|
| News + filings | Finnhub `/company-news`, `/stock/filings` | free tier OK, cache per addendum-1 budget |
| Float / shares outstanding | Finnhub basic financials IF present; else FMP free tier `/profile` | VERIFY availability first; if neither returns float, tier by shares outstanding as proxy and label it "SO-proxy" |
| Daily OHLCV | existing OHLC source (same as MAE/MFE backfill) | fine |
| Relative volume | intraday candles — Finnhub free tier does NOT include US candles | Option A: compute rel-vol on DAILY volume only (v1, honest and free). Option B: add a free intraday source later. Ship v1 with daily rel-vol; label it clearly. |

rel_vol (v1, daily) = today's cumulative volume / 20d avg volume at same time-of-day if
intraday available, else full-day vs 20d avg (updates after close + premarket estimate).

## FOUR LANES (sub-tabs) — each with its own rubric, own stats, own learnings entry
Every trigger row stores `lane` ('runner'|'bounce'|'value'|'hailmary'). Stats are broken
out per lane AND in aggregate. This is the whole point: after ~40 trades you will know
which lane is actually yours, instead of averaging four different edges into mush.

### LANE 1 — "Runners" (< 20M float explosives)
1. float < 20M (the mini-tab; display float in M on every card)
2. rel_vol ≥ 3.0
3. catalyst within 48h (news cache) — headline shown inline
4. price holding above prior day's close
5. dilution_risk = false AND not on deathwatch
Band: scalp only (1-3d), time-stop 3d. Size: small — these gap and fail violently.
Score = rel_vol (35) + catalyst quality (25) + float tightness (20) + structure (20).

### LANE 2 — "Demand Bounce" (oversold at real demand, PROVEN — not any bounce)
ALL required:
1. downtrend context: price < 20d SMA and ≥ 30% off 60d high
2. AT A REAL LEVEL: within 3% of a prior swing low that held ≥ 2x before, OR a prior
   consolidation shelf, OR the 200d SMA. "Oversold" alone (RSI < 30) is NOT a level —
   RSI is a supporting flag, never the reason.
3. SELLING EXHAUSTION: avg volume of last 3 red days < 0.7x the 20d avg (sellers drying
   up BEFORE the turn)
4. DEMAND CONFIRMATION — at least 2 of 3 on the trigger day:
   a. rel_vol ≥ 3.0 AND close in upper third of day's range
   b. undercut-and-reclaim: low < prior 10d low AND close > prior 10d low
   c. reclaim of prior day's high on a green close
   → store as `demand_signals[]`; the learnings loop reveals which combo actually
   predicts follow-through
5. dilution_risk = false; not on deathwatch
Band: swing 1-5d, time-stop 5d. This is the best-R:R lane — targets at the prior
consolidation, stops under the level. Score = demand_signals count (30) + level quality
(25) + exhaustion (20) + rel_vol (15) + catalyst if any (10).

### LANE 3 — "Quality Value" (cheap ≠ garbage — the diamond-hands lane)
The only lane allowed to hold for weeks. Requires FUNDAMENTALS, not just charts:
1. revenue > $20M TTM AND revenue growth > 0% YoY (it's a real business)
2. gross margin > 15% (it isn't selling dollars for ninety cents)
3. cash runway: cash / quarterly burn > 4 quarters, OR positive operating cash flow
   (this single check kills most sub-$5 traps)
4. debt/equity < 2.0
5. UPTREND: price > 20d SMA AND > 50d SMA, 50d slope positive
6. NOT a recent runner (excluded if up > 50% in 10 days — you're buying a base, not a top)
7. dilution_risk = false; not on deathwatch (mandatory here)
Band: position, 3-8 weeks, time-stop 8w. Score = fundamentals composite (40: revenue
growth, margin, runway, D/E) + trend quality (30) + valuation vs sector (20: P/S or EV/S
percentile within sector_name) + catalyst (10).
This lane gets a "why this isn't garbage" section in the thesis note, citing the actual
revenue/margin/runway numbers. Fundamentals from Finnhub basic-financials; if a field is
missing, the symbol is DISQUALIFIED from this lane (no proxies here — a value thesis on
guessed fundamentals is worthless).

### LANE 4 — "Hail Mary" (explicitly speculative, caged)
Honest lane for the lottery tickets. Fires on: extreme rel_vol (≥ 5.0) + catalyst +
float < 30M, WITHOUT requiring the demand/exhaustion structure the other lanes demand.
HARD CAGE RULES (enforce in code, display on the tab):
- fixed notional size, never scaled, regardless of any win streak
- max 2 open hail-marys at a time
- own stats, never blended into the other lanes or the aggregate expectancy headline
- can never graduate to live trading — permanently paper. This tab is a hypothesis lab.
- deathwatch still applies. Speculative ≠ suicidal.
Tab renders with a distinct (amber) treatment so it never reads like a signal.


## The page itself
Route: /smallcaps. Sub-tabs across the top: **Runners** | **Demand Bounce** |
**Quality Value** | **Hail Mary** (amber) | **All**
- Filter chips (per tab): float tier, sector, dilution flag, rel_vol slider, catalyst
  present; on Value additionally: revenue-growth / margin / runway sliders
- Main: CARD list (not table) — symbol, price, float in M + tier badge, rel_vol, lane,
  score, dilution flag (red), demand_signals chips, and the CATALYST HEADLINE inline
  with source + age. Value cards additionally show revenue, growth %, gross margin, and
  cash runway ON THE CARD FACE — the fundamentals ARE the thesis in that lane.
  Click -> detail drawer: thesis JSON (main-spec Lane 3 format), levels, symbol news
  list, filings list, and for Value: the "why this isn't garbage" section citing real
  revenue/margin/runway numbers.
- Bottom strip: "sector heat" — trigger count per sector today (cheap names moving in a
  sector before the mid-caps confirm it — the 'undervaluation in sectors' view)
- Collapsible "Excluded (deathwatch)" list at page bottom with per-name reason
- Paper trades write to paper_trades with book='smallcap' AND lane=<lane>
  (new columns `book`, `lane`; backfill book='swing' on all existing rows — additive)

## Stats + learnings (PER LANE, never blended)
- /smallcaps/record: reuse the Lane-5 sort/filter component, filtered book='smallcap',
  with a lane selector. Stat cards render PER LANE, plus an aggregate that EXCLUDES
  hailmary.
- own learnings_smallcap.json, keyed by lane, same n >= 8 promotion / auto-demote rule
- graduation rule displayed per lane: "Paper only. Live-eligible at n >= 30 closed,
  expectancy > +0.15R, max drawdown < 10R." Hail Mary is permanently paper and says so.
- HEADLINE QUESTION the page must answer within ~40 trades: WHICH LANE IS ACTUALLY MINE?
  Render a lane-comparison table at the top of /smallcaps/record: lane, n, expectancy,
  win rate, avg hold, best R, worst R. That table is the entire point of splitting the
  lanes — do not bury it.

---

## CROSS-CUTTING SIGNALS (apply across all four lanes)

### A. Sector trickle-down — "early to the pop" (reuse Lane-4 infra, high value)
Sector strength leads the small caps in that sector. You already compute weekly sector
bias + RS vs SPY for the 11 SPDRs in main-spec Lane 4 — pipe it DOWNWARD:

- `sector_heat_score` per sector, daily = (sector ETF weekly bias: bull=1/neutral=0/bear=-1)
  + (sector RS vs SPY 5d percentile) + (count of sub-$5 names in that sector triggering
  any lane today, normalized)
- NEW SIGNAL `sector_early`: fires when a sector's ETF turned bullish within the last
  10 sessions AND that sector's small-cap trigger count is rising week-over-week, but the
  sector's MID-caps have not yet broken out. That's the "we're early" window.
- Any trigger in a `sector_early` sector gets +10 score and a `SECTOR EARLY` chip on the
  card. Low-float names in a heating sector are exactly the pop-off setup — this catches
  them before the crowd.
- Sector heat strip at page bottom sorts by sector_heat_score desc, with a flame icon on
  `sector_early` sectors.

### B. Bollinger compression — the $SUNE tell (daily squeeze on small caps)
The swing book has squeeze logic; small caps need their OWN, tuned for volatility:
- `bb_width = (upper20,2 - lower20,2) / mid20`
- `bb_percentile` = today's bb_width vs its own trailing 120d distribution
- SIGNAL `daily_compression`: bb_percentile <= 10 (bottom decile — historically tight FOR
  THIS NAME, which is the point; a small cap's "tight" is a large cap's "wild")
- SIGNAL `compression_extreme`: bb_percentile <= 5 AND >= 5 consecutive days in the bottom
  decile — this is the $SUNE-style coil. Gets its own `COILED` chip + a dedicated filter,
  and +15 score in any lane.
- Direction is UNKNOWN in a squeeze — do not predict it. The trigger is the EXPANSION:
  first close outside the bands on rel_vol >= 2.0 sets direction. Store `squeeze_days` so
  you can see how long it coiled (longer coil = bigger expansion, generally).
- Add a standing "Coiled Watchlist" section on the page: names currently in
  compression_extreme that have NOT yet expanded. This is the watch-and-wait list — the
  thing you check every morning.

### C. Baseline screen defaults (your Finviz workflow, encoded as presets)
Preset filter sets, selectable from a dropdown so the page opens the way you actually scan:
- **"Standard"**: float < 500M · volume > 500k · rel_vol > 0.75 · price target (analyst
  mean) > current price · weekly close > prior weekly close (up week-over-week)
- **"Volatile"**: float < 50M · same volume/rel_vol gates
- **"Aggressive"**: float < 30M
- **"Micro"**: float < 10M
- Weekly trend flag `up_wow`: this week's close > last week's close. Add a
  `consecutive_up_weeks` counter (1-8+) — it's a clean, cheap trend read, filterable and
  sortable. Trend > snapshot.
- Analyst price target: Finnhub `/stock/price-target` (free tier — VERIFY; if unavailable,
  omit the field entirely and say so; do NOT substitute a made-up target). Display
  `upside_to_target_%` on the card when present. Treat as ONE input among many — analyst
  targets on small caps are frequently stale and often wrong.

### D. Options / LEAPS overlay (screening flag only, informational)
For names that pass any lane, check whether options are even tradeable — most sub-$5 names
have unusable chains, so this is a filter, not a strategy:
- `has_options` (Finnhub option-chain lookup)
- `options_liquid`: >= 3 expirations available AND open interest >= 500 on at least one
  strike near the money AND bid-ask spread <= 15% of the mid on that strike
- `has_leaps`: an expiration >= 9 months out exists AND meets the liquidity bar above
- Card shows a small `LEAPS` chip only when `has_leaps` is true. Clicking shows the
  furthest liquid expiry, its ATM strike, OI, and spread — raw facts, no recommendation.
- Restrict LEAPS chips to the **Quality Value** lane by default (a multi-month option on a
  3-day momentum thesis is a mismatch), with a toggle to show them everywhere.
- This overlay does NOT feed scoring or verdicts. It answers one question: "is there even
  a liquid chain here?" All sizing/strike/structure decisions stay with you.
- If Finnhub's free tier lacks option chains, render the chip as unavailable and tell me —
  do not fabricate liquidity data.

### E. New filterable flags summary (add all to the facet list)
`sector_early` · `daily_compression` · `compression_extreme` · `squeeze_days` ·
`up_wow` · `consecutive_up_weeks` · `upside_to_target_%` · `has_options` ·
`options_liquid` · `has_leaps` · `demand_signals[]` · `dilution_risk` · float tier

---

## Build slot
After Phase 5 (needs the news cache + bias panel infra). Before Phase 6 is fine if
desired — it shares the thesis-note format but not the learnings file.