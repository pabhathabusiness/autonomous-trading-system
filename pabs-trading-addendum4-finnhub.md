# Addendum 4 — Using Finnhub Properly (free tier is 5x underused)
Every endpoint PROBED FIRST. Verify free-tier availability, never fake a field, report premium.
---
## PART 1 — PROBE (report: endpoint | free? | sample)
`/stock/insider-transactions` (HIGHEST), `/stock/insider-sentiment` (HIGH MSPR),
`/stock/earnings` (HIGH surprise history), `/stock/recommendation` (MEDIUM, price-target is
premium), `/stock/peers` (MEDIUM), `/stock/metric` series object (HIGHEST time-series),
`/stock/social-sentiment` (LOW), `/stock/split` (confirm), `/calendar/ipo` (LOW).
403 -> log, move on, do not substitute.
---
## PART 2 — INSIDER ACTIVITY (new edge family `insider`)
From `/stock/insider-transactions` (6mo): insider_buy_count/sell_count (distinct),
insider_net_shares, insider_net_dollars (signed), insider_buyers_distinct,
insider_cluster (>=2 distinct insiders bought within 30d), last_insider_buy_days_ago.
EXCLUDE from "buying": option exercises/grants (codes 'M','A','G'). Only OPEN-MARKET
purchases (code 'P') count.
Scoring (0-1): cluster within 90d ->1.0; single open-market buy >$50k within 90d ->0.7;
net$ positive no cluster ->0.4; net$ negative (heavy selling) ->0.0 AND -0.5 composite
penalty; no data ->0.0 no penalty.
Lane weights insider: Special 2.0 · Value 2.5 · Bounce 1.5 · Coiled 0.5 · Runner 0.5 · HailMary 0.0
Card: `INSIDER BUY` chip green `2 insiders · $180k · 12d ago`. If insider-sentiment free, store MSPR 3mo trend.
---
## PART 3 — NEWS: CLASSIFY, DON'T COUNT
### 3.1 Catalyst taxonomy (keyword rules first, LLM fallback for leftovers)
| Type | Keywords | Weight |
|---|---|---|
| contract_award | contract, award, order, partnership, agreement, selected by | +1.0 |
| regulatory_win | FDA approval, clearance, 510(k), designation, patent granted | +1.0 |
| earnings_beat | beats, exceeds, record revenue, raises guidance | +0.9 |
| analyst_upgrade | upgrade, initiated coverage, raised to buy | +0.5 |
| insider_buy_news | insider purchase, director buys | +0.6 |
| product_launch | launches, unveils, begins shipping | +0.4 |
| neutral_pr | participation in conference, presents at, webcast | 0.0 |
| offering | offering, pricing of, registered direct, ATM, warrant, dilut | -1.5 |
| going_concern | going concern, substantial doubt, restructuring, Chapter 11 | -2.0 + HARD PASS |
| earnings_miss | misses, lowers guidance, withdraws guidance | -0.8 |
| delisting | deficiency, non-compliance, delisting notice | -1.5 |
| dilution_risk | reverse split announced | -1.0 |
CRITICAL BUG FIX: offering/going_concern currently pass as POSITIVE. A stock spiking on an
offering is spiking DOWN. Highest-value single fix in this addendum.
### 3.2 News velocity: news_count_7d vs baseline_90d; velocity=count_7d/(baseline_90d/13).
Spike (>3x) WITHOUT price move -> `NEWS SPIKE` chip, feeds catalyst family.
### 3.3 Source quality: major wire (Reuters/Bloomberg/AP/DowJones)=1.0; company PR
(GlobeNewswire/PRNewswire/Businesswire)=0.5; aggregators/blogs=0.25.
---
## PART 4 — FUNDAMENTAL TRENDS (`series` object)
From `/stock/metric` series (quarterly/annual): revenue_trend (accel/stable/decel over 4q),
margin_trend, current_ratio_trend, shares_outstanding_trend (solves deathwatch rule d:
>100% share growth 12mo — probe for it), eps_trend.
Trend weighted ~40% of fundamental family: rising 15% margins > falling 20%.
New chip `REV ACCEL` (green) when revenue growth accelerating 3 quarters running.
---
## PART 5 — EARNINGS SURPRISE (`/stock/earnings`)
beat_streak, avg_surprise_pct (last 4), last_surprise_pct. Feeds fundamental family +
`BEAT x3` chip. Earnings-proximity penalty scaled by miss volatility, not flat.
---
## PART 6 — 52W RANGE + BETA (already in /stock/metric)
pct_of_52w_range=(price-low)/(high-low). Bounce wants <0.25. Special/Value want rising off
low base. beta -> sizing + risk chip. pct_from_52w_high displayed on every card.
---
## PART 7 — PEER-RELATIVE VALUATION (`/stock/peers`)
Fetch peers, pull P/S & EV/S, compute candidate percentile vs REAL peers not XLV writ large.
Cache 30d. Feeds fundamental family valuation sub-score.
---
## PART 8 — RECOMMENDATION TRENDS (probe; price-target is premium)
`/stock/recommendation` buy/hold/sell counts over time. analyst_coverage_count,
recommendation_trend. Weak evidence (0.3 weight inside catalyst family). Display, don't lean.
---
## PART 9 — MARKET NEWS -> REGIME
Count risk-off (recession, selloff, hawkish, tightening, crisis, plunge) vs risk-on (rally,
record high, dovish, cut) in last 24h general news. news_regime_tilt = soft TIEBREAKER only
when technical regime=chop. Never overrides technicals.
---
## PART 10 — EDGE-FAMILY TABLE (final, adds insider)
`volume · structure · compression · trend · fundamental · catalyst · sector · float · insider`
| Lane | vol | struct | compr | trend | fund | catal | sector | float | insider |
|---|---|---|---|---|---|---|---|---|---|
| Special  | 0.5 | 1.5 | 1.5 | 2.0 | 3.0 | 1.0 | 0.5 | 0.0 | 2.0 |
| Value    | 0.5 | 1.0 | 1.0 | 2.0 | 3.5 | 0.5 | 0.5 | 0.0 | 2.5 |
| Bounce   | 2.0 | 3.0 | 1.0 | 0.0 | 0.5 | 1.5 | 1.0 | 1.0 | 1.5 |
| Coiled   | 1.5 | 1.5 | 3.5 | 0.5 | 0.0 | 1.0 | 1.0 | 1.0 | 0.5 |
| Runner   | 3.0 | 1.0 | 1.5 | 0.5 | 0.0 | 2.5 | 1.0 | 1.5 | 0.5 |
| HailMary | 3.5 | 0.5 | 1.0 | 0.0 | 0.0 | 3.0 | 0.5 | 1.5 | 0.0 |
3-independent-families rule still governs. insider counts as full independent family.
---
## PART 11 — RATE BUDGET
Universe ~150-400 after A3 fixes. Enrichment only on shortlist. Cache: peers 30d · insider 3d
· earnings 7d · metrics 3d · filings 1d · news 15min. Sequential ~1.1s. ~1,600 calls ~30min
once then cached. Background thread.
