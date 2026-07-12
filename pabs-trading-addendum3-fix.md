# Addendum 3 — Small Caps FIX + Price Tiers + Multi-Edge Scoring
Supersedes conflicting parts of Addendum 2. Everything else in Addendum 2 stands
(quarantine, deathwatch, book='smallcap', paper-only, per-lane stats).
---
## PART 1 — WHY ZERO TRIGGERS (fix these first, in order)
### 1.1 The float cap is wrong — RAISE IT
Current: universe capped at float <= 100M. Rejected SNDL/PLUG/BBAI/GEVO for float.
Those are the liquid movers. Cheap stocks are cheap BECAUSE share count is high.
NEW universe float ceiling: **<= 500M** (matches the user's Finviz "Standard" screen).
Float is now a TIER + SCORE INPUT, never a universe gate:
- `runner   < 20M`
- `low      20-50M`
- `mid      50-150M`
- `standard 150-500M`
Score bonus scales inversely with float (tighter = more explosive), but nothing is
excluded for being "too big" under 500M.
Also: SO-proxy inflates float. Where `profile2` shares-outstanding is the only source,
apply a documented `float_est = shares_outstanding * 0.85` haircut ONLY for tier
display, and label the field `SO-proxy (est)`. Never present it as true float.
### 1.2 Gates -> Scores (the core architectural fix)
DELETE the ANDed hard gates from all four lanes. Only these remain HARD (true
disqualifiers, nothing else):
- deathwatch (reverse splits, dilution-form flag)  [see 1.4 for the sub-$1 change]
- liquidity floor: 20d avg $ volume >= $300k  (lowered from $500k)
- exchange-listed (no OTC)
Everything else becomes a WEIGHTED EDGE. A name scores; it does not "pass".
### 1.3 rel_vol thresholds were built for intraday data we don't have
Free tier = daily rel_vol only. Recalibrate:
`rel_vol_score = clamp((rel_vol - 1.0) / 2.0, 0, 1)`  -> 1.5x scores 0.25, 3.0x scores 1.0.
Nothing is rejected for rel_vol; it just scores lower.
### 1.4 Sub-$1 deathwatch conflicts with the user's sub-$1 tier
- Rule (e) is DOWNGRADED from a hard exclusion to a **scored penalty** (-1.5) and a
  red `DELISTING RISK` chip, and applies ONLY outside the Deep Speculative tier.
- Reverse-split and dilution-form deathwatch rules stay HARD everywhere.
### 1.5 Run the full universe build
`smallcap.enabled` ON, full ~5,124-name build. Log universe size after build.
If universe < 150 names after fixes, report which filter is over-filtering.
---
## PART 2 — PRICE TIERS
| Tier | Price | Max hold | Options expected? |
|---|---|---|---|
| `special`  | $5.00-10.00 | 8 weeks | YES (required for Special lane) |
| `low`      | $2.00-5.00  | 5 days | Sometimes |
| `sub2`     | $1.00-2.00  | 5 days | Rare |
| `deep`     | $0.20-1.00  | 3 days | Almost never |
`deep` tier: fixed tiny notional, max 3 open, permanently paper, reverse-split+dilution
deathwatch still HARD, own stats excluded from every aggregate.
---
## PART 3 — NEW LANE: "Special" ($5-10, optionable, high quality)
HARD requirement (only one): `options_liquid = true`. No chain, no lane.
Scored edges: fundamentals (rev>$50M TTM, growth>0, GM>20%, +OCF or runway>6q, D/E<1.5),
valuation (P/S or EV/S bottom 40% of sector), trend (>20d & >50d SMA, 50d slope+, up_wow),
setup (breakout OR compression_extreme OR at-a-real-level bounce), catalyst (news 7d or
upcoming date), optionality (LEAPS bonus + card shows furthest liquid expiry/ATM/OI/spread).
Band: position, 3-8 weeks. The only cheap lane that may hold.
---
## PART 4 — MULTI-EDGE SCORING
0-10 composite from EDGE FAMILIES. Trigger requires BOTH:
1. composite_score >= 7.0
2. >= 3 independent edge families firing (each family >= 0.5)
Families: volume, structure, compression, trend, fundamental, catalyst, sector, float.
Composite = weighted sum normalized to 0-10. Lane weights:
| Lane | volume | structure | compression | trend | fundamental | catalyst | sector | float |
|---|---|---|---|---|---|---|---|---|
| Special   | 0.5 | 1.5 | 1.5 | 2.0 | 3.0 | 1.0 | 0.5 | 0.0 |
| Value     | 0.5 | 1.0 | 1.0 | 2.0 | 3.5 | 0.5 | 0.5 | 0.0 |
| Bounce    | 2.0 | 3.0 | 1.0 | 0.0 | 0.5 | 1.5 | 1.0 | 1.0 |
| Runner    | 3.0 | 1.0 | 1.5 | 0.5 | 0.0 | 2.5 | 1.0 | 1.5 |
| HailMary  | 3.5 | 0.5 | 1.0 | 0.0 | 0.0 | 3.0 | 0.5 | 1.5 |
The 3-independent-families rule is what "multi-edge" means: a name that is ONLY a volume
spike cannot reach a trigger. Display composite `8.2/10` + family chips that fired.
Threshold tunable, tuned by data. Start 7.0. <3 triggers/week -> log THRESHOLD DIAGNOSTIC
(top 20 by composite w/ family breakdown). Never silently lower — surface it.
---
## PART 5 — OPTIONS DATA (use yfinance, Finnhub option-chain is premium/403)
`t=yf.Ticker(sym); expiries=t.options; chain=t.option_chain(exp)` -> .calls/.puts with
strike, bid, ask, volume, openInterest, impliedVolatility. Cache daily.
- has_options = len(expiries)>0
- options_liquid = >=3 expiries AND nearest-ATM of a >30d expiry: OI>=250 AND (ask-bid)/mid<=0.20
- has_leaps = expiry >=270d out meets same liquidity bar; store leaps_expiry/atm/oi/spread
REALITY: sub-$1 essentially never have options; sub-$2 rarely. Expect has_options=false for
most sub2/deep. LEAPS requirement lives in Special lane, bonus in low. Not offered below $2.
yfinance unavailable/rate-limited -> options: unavailable. Never infer.
---
## PART 6 — VALIDATION (before declaring the fix works)
Backtest-style dry scan, last 30 trading days on rebuilt universe. Report universe size,
triggers/day/lane, composite histogram, family-firing frequency, top 20 w/ breakdowns,
biggest-filter diagnostic. ACCEPTANCE ~2-8 triggers/day. Zero=over-filtered. >20=raise.
Report BEFORE wiring to auto-open paper trades.
