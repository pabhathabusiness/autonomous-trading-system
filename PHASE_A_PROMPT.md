# PHASE A BUILD — Sector Relation Engine + Bugs + Options First-Class
Read NORTH_STAR_v2.md first. It is the authority on trader profile and architecture.

Confirmed profile updates (this session):
* Can place/adjust orders from PHONE ANYTIME -> intraday alerts are actionable. Day trades
  and overnight trades are IN. But alerts are event-driven pings, never "sit and watch."
* OPTIONS ARE ~50% OF HIS TRADING. Options is FIRST-CLASS, not an overlay. Every idea needs
  an options expression alongside the shares expression.
* Priority: (1) Sector Relation Engine, (2) bugs + empty small-cap page, (3) Asymmetry
  lane, (4) free-roll.

## A0 — VERIFY yfinance INTRADAY (gates day/overnight work)
Probe and report: for a mid-cap and a $3 small-cap, what does yfinance return for
interval=1h / 15m / 5m, and how far back? Report actual bar counts and date ranges.
If intraday is unavailable/unreliable for small caps, SAY SO and restrict day trades to
liquid names only. Do not fabricate intraday timeframes we cannot compute (see BUG-4).

## A1 — THE SECTOR RELATION ENGINE (priority 1 — the differentiator)
### A1.1 Universe of nodes
Core 11 SPDRs + themes: LIT BATT REMX XME COPX SIL GDX URA NLR TAN ICLN FAN QCLN PBW GRID
SMH SOXX IGV SKYY HACK CIBR BOTZ ROBO ARKK ARKX ITA PPA XOP OIH XLE JETS IYT XRT XHB ITB
PAVE MOO WOOD KRE IAI IBB XBI IHI DRIV IDRV (verify each has sufficient history; drop any
that don't).
### A1.2 Lead-lag matrix (MEASURED — this is the core)
Rolling 6-month window, recomputed weekly. Daily returns for every node. For each ordered
pair (A,B) and lag k in 1..10: xcorr(A_t-k, B_t) Pearson on returns. best_lag(A->B)=argmax_k,
strength=that corr. A LEADS B iff strength(A->B,k>=1) > corr(A,B,lag0)+0.05 AND strength>=0.45
AND holds in >=2 of the last 3 non-overlapping 2-month sub-windows (stability). Store leader,
follower, lag_days, strength, stability_score, n_obs, last_confirmed. Report how many pairs
clear the bar — do not lower the bar to manufacture relationships.
### A1.3 Theme graph (hand-seeded, machine-validated)
Seed theme_graph.json (ai_datacenter/battery/oil/rates/space per NORTH_STAR §3.2). Each
edge VALIDATED against the measured matrix; unsupported edges marked `unvalidated`, greyed,
not used for scoring.
### A1.4 SYMPATHY SETUP detection (the money feature)
Per validated edge U->D daily: (1) U RUNNING (weekly bull AND 5d>+2% AND >20d SMA); (2) D
NOT moved (5d<+1% AND <0.5 ATR above 20d SMA); (3) lag window OPEN (days since U move <
lag_days+3). If all three -> SYMPATHY SETUP. Rank names in D by Emerging Strength; surface
top 5. Exact card copy: "SYMPATHY: XLE -> XOP ... Window closes in 3 days. Names not yet
extended: [ranked]." Own page section + push alert.
### A1.5 Sector regime board
Rank all nodes by 20d RS vs SPY. Show STRONGEST 3 + WEAKEST 3. Compute RANGE + demand/supply
zones for SPY, QQQ, top/bottom sectors. This IS the chop playbook.
### A1.6 Bottleneck watch (hypothesis generator, not a trade signal)
bottleneck_watch.json: theme -> {ETF proxies, pure-plays, narrative_velocity from news
clustering}. Divergence (cluster trend_score rising while ETF flat) = hunting ground.
Display only. Print: "Hypothesis generator — technicals must confirm."

## A2 — OPTIONS AS FIRST-CLASS (user is ~50/50 options)
Every idea, every lane, BOTH expressions side by side.
### A2.1 Chain data (yfinance)
Per candidate cached daily: expirations, strikes, bid, ask, volume, OI, IV. options_liquid
= >=3 expiries AND near-ATM on >30d expiry with OI>=250 AND (ask-bid)/mid<=0.20. Else
SHARES ONLY. Never fabricate.
### A2.2 IV RANK — the key synergy
iv_rank = percentile of ATM IV vs trailing 252d (0-100). COILED + iv_rank<30 = cheap
optionality on anticipated expansion -> flag loudly "COILED · IV RANK 12 — options cheap"
(the single best options setup for this trader). iv_rank>70 -> options expensive, favor
shares/spreads. Display iv_rank on EVERY options expression.
### A2.3 Options expression on each card (facts, not orders)
Suggested expiry window >= time_stop x 2 (never expire while thesis valid). Nearest liquid
strikes at/above trigger with bid/ask/OI/IV. iv_rank + cheap/fair/expensive. Breakeven vs
share target ("share target $8.20 below the $9 call breakeven $9.40 — does not pay").
EVENT WARNING: earnings/binary inside expiry -> IV CRUSH RISK. Structure/size stays user's.
### A2.4 Free-roll with options
Ladder on CONTRACT COUNT; partial exits lumpy. If <3 contracts: "free-roll not practical."

## A3 — BUGS (priority 2 — immediately after A1)
- BUG-1 R:R floor not enforced (GOOGL 356/351/358 = 0.4:1). Enforce in plan constructor;
  rr<floor -> DO NOT EMIT, log rejected_rr. Floors: day 1.5·overnight 1.8·swing 2.0·position
  2.2. Regression test. Report existing open trades below floor.
- BUG-2 stance/direction incoherence (bearish -> LONG). Assert stance==direction or
  counter_trend=true explicit+displayed, else reject + log rejected_incoherent.
- BUG-3 Mag7/index NO trade plan. Hard-exclude AAPL MSFT NVDA AMZN GOOGL META TSLA + SPY QQQ
  IWM DIA RSP + 11 SPDRs from every lane/emitter. Briefing cards separate; no entry/stop/
  target can structurally render. Header "Context only — no trade plan."
- BUG-4 the "1hr trigger" on GOOGL. Find its source. If fabricated/mislabeled-daily, remove.
  After A0, if 1h available, rebuild honestly on real 1h bars.
- BUG-5 COMPOSITE CEILING (why small-cap page is empty). Missing family LOWERS the ceiling.
  FIX: composite = sum(w_i*f_i for AVAILABLE i)/sum(w_i for AVAILABLE i)*10. Distinguish
  UNAVAILABLE (no data exists -> excluded from denominator) from AVAILABLE-AND-ZERO (data
  exists, signal absent -> stays in denominator). Keep >=3-family rule. FIRST report
  theoretical-max-composite per lane BEFORE fixing.
- BUG-6 never blank. Always render TOP 20 per lane by composite, triggered or not. Below-bar
  show "6.1/6.5 — below bar" + missing family. Add "why nothing triggered" line.
- BUG-7 Coiled watchlist renders on every tab -> scope to its own tab.
- BUG-8 reverse-split hard exclusion too harsh (FCEL). Change to TAG + scored penalty
  (-0.75) + R-SPLIT chip. HARD only for: 2+ reverse splits in 5y, OR reverse split PLUS
  active dilution filings (zombie signature).

## A4 — ADD THE MISSING LANES (rename to theses per NORTH_STAR §3/§7)
Turnaround · Oversold Reversal · Hidden Value · Breakout (WAS MISSING) · Compression ·
Emerging Strength. Delete Runner and HailMary (lottery lanes; fold good parts into Breakout
+ Emerging Strength).

## REPORT
1. A0 intraday availability. 2. A1.2 how many pairs cleared the bar + top 10 with lags/
strengths. 3. A1.4 how many sympathy setups fire today. 4. BUG-5 theoretical-max-composite
table (before fix). 5. BUG-1 open trades below floor. 6. A2.2 iv_rank distribution + how many
COILED with iv_rank<30.

## PLUS — P3 FIX (num_edges anti-predictive, rho=-0.398)
Port the small-cap family-collapse to the SWING grader (replace raw edge count with
independent family count: *_squeeze collapse to 1 + 0.25 per extra TF, cap 1.5). Keep old
score as quality_raw; print before/after for top 10 open proposals. Re-run Spearman with
FAMILY COUNT; report whether rho improves. Do NOT otherwise retune (n=24 too small). Longer
term the two scoring systems should MERGE — report what that takes.

## Guardrails
auto_execute FALSE · paper only · new/NULL columns only · never modify resolve_open,
close_on_live_cross · 78 legacy rows survive every change · secret-scan every diff · snapshot
before migration · commit per unit.
