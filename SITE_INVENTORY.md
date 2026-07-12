# SITE_INVENTORY.md — read-only ground truth (2026-07-12)

Scope: what EXISTS, what RENDERS, what is DEAD, the two scoring systems, and the
open contradictions. Nothing was changed to produce this. "Verified live" = I
queried the running server; "from code" = read from source, not confirmed on screen.

---

## 1.1 — What EXISTS vs what RENDERS

Frontend is one SPA (`index.html` + `app.js`) with 5 nav views + a news drawer.
Backend is FastAPI (`api_server.py`). Table below; "empty?" = renders but is
often/always blank.

| Surface | Route / loader | Backend? | Renders? | Real data? | Dead / notes |
|---|---|---|---|---|---|
| Dashboard ▸ Market Context (VIX/breadth/econ/news/earnings) | `/api/market-overview` | yes | yes | partial | VIX intermittently null (yfinance ^VIX); news+earnings now Finnhub-backed (verified) |
| Dashboard ▸ **Market Bias strip** (SPY+mega) | `/api/bias-strip` → `bias_strip.build` | yes | yes | **yes but MISLEADING** | **conditional/daily bias; SPY+4 mega = "Neutral" right now. THIS is the P1 the user saw. See 1.6.** |
| Dashboard ▸ Sector Strength board | `/api/sectors` | yes | yes | yes | sector rankings from sector_analyzer |
| Dashboard ▸ Weekly Bias & Regime | `/api/market-bias` → `mtf_bias` panel | yes | yes | yes | SPY/QQQ/sectors bullish (verified). **Disagrees with the strip above.** |
| Dashboard ▸ Trade Ideas feed | `/api/log/algo` | yes | yes | yes | the algo book (78 rows) |
| Track Record | `/api/log/algo` (+track-record) | yes | yes | yes (78) | retro-grades/quadrants/MAE-MFE render |
| Small Caps ▸ Runners/Coiled/Bounce/Value/Special/HailMary/All | `/api/smallcap/triggers` | yes | yes | **usually EMPTY** | BUG-5 composite ceiling; ~1006-name universe but 0-2 triggers. Special never fires (no options module). |
| Small Caps ▸ Coiled watchlist | universe `compression_extreme` | yes | yes | maybe | **BUG-7: renders on every tab** |
| Small Caps ▸ Sector heat strip | `mtf_bias` panel + counts | yes | yes | yes | reuses Lane-4 panel |
| Small Caps ▸ Deathwatch | `/api/smallcap/deathwatch` | yes | yes | yes (~209) | |
| Small Caps ▸ Lane Record | `/api/smallcap/record` | yes | yes | ~0 closed | per-lane table exists; little data yet |
| Sectors view | `/api/sectors`, `/api/sector/{}/setups` | yes | yes | yes | heatmap + drill-down |
| More ▸ Regime/Accounts/Performance | `/api/regime` `/api/accounts` `/api/performance` | yes | yes | yes | |
| More ▸ Proposals tabs (Top/Short/Coiling/Downside/Sector/Timeframe) | `/api/proposals` | yes | yes | yes | the OLD main scanner's proposals |
| News drawer (chip click) | `/api/news/symbol` `/api/news/sector` `/api/earnings/upcoming` | yes | yes | yes | per-symbol cached news + EPS badge |
| News clusters | `/api/news/clusters` | yes (P4, just deployed) | **NO frontend yet** | building | backend live; no UI consumes it |
| Live snapshot | `/api/live`, WebSocket loop | yes | partial | Alpaca-dep | built early; usage thin — **candidate dead code, verify** |
| `/api/turning-sectors`, `/api/drilldown/{}` | routes exist | yes | drilldown yes (More) | — | turning-sectors usage unclear — verify |

**Empty-page reality:** the Small Caps page is the headline problem. The universe
builds (~1006 names) but the scoring almost never clears the bar (BUG-5), so the
lanes render blank. There is no "top 20 anyway" fallback (BUG-6).

---

## 1.2 — THE TWO SCORING SYSTEMS (most important section)

There are two independent engines with **different purposes**, which is the root
confusion. One GRADES an already-chosen trade's discipline; the other SELECTS
candidates. They are not the same kind of number.

### A. SWING grader — `process_grader.grade` (Log B / algo book)
- **Purpose:** score DECISION QUALITY of a setup, outcome-independent → letter A–F.
- **Inputs:** an `analyze()` dict (archetype, entry/stop, risk_reward, `dim_scores`
  = 5 capped dims [structure/momentum/volatility/volume/rel_strength], `num_edges`,
  daily/weekly bias, patterns, rs_vs_spy) + sector context.
- **Weights (sum 100):** entry_discipline 26 · timeframe_confluence 18 ·
  confluence_breadth 16 · stop_at_structure 14 · rr_quality 12 · sector_alignment 8
  · rel_strength 6. → 0–100 → A≥88 B≥78 C≥68 D≥55 else F.
- **Emits:** `{grade, score, flags, notes, subscores}` stored on each paper trade.
- **The P3 defect:** `num_edges` (raw count) correlates **−0.398** with realized R.
  It enters here two ways: `confluence_breadth` mainly counts ACTIVE DIMENSIONS
  (already family-like) but adds a `+0.05` nudge when `num_edges≥8` — and the raw
  count is stored/used elsewhere. High-edge names underperformed.

### B. SMALLCAP engine — `smallcap_lanes.py` (book='smallcap')
- **Purpose:** SELECT/trigger candidates → 0–10 composite; fires when
  `composite ≥ 6.5 AND ≥3 independent families ≥0.5`.
- **Inputs:** a universe row + `signals` (9 families: volume, structure,
  compression, trend, fundamental, catalyst, sector, float, insider).
- **Weights:** per-lane weight table (A4 Part 10); composite =
  `10 · Σ(family·w)/Σ(w)` + penalties (offering/delisting/insider-selling).
- **Emits:** triggers (lane, composite, families_fired, band, chips) → paper trades.
- **Its own defect:** BUG-5 — composite normalizes over ALL weights, so a family
  with NO DATA lowers the ceiling instead of being excluded → the page is empty.

### Where they diverge
| | Swing grader | Smallcap engine |
|---|---|---|
| Question | "how disciplined was this entry?" | "should this name fire today?" |
| Output | A–F (0–100) | 0–10 composite + trigger gate |
| Edge logic | active-dimension count + num_edges nudge (**anti-predictive**) | independent-family count, ≥3 rule (**the intended fix**) |
| Missing data | subscores fall back to conservative-neutral | family scored 0 (drags composite — BUG-5) |
| Runs on | main-scanner proposals (swing/short/coiling/downside) | sub-$5 universe |

### **Could the swing grader use the small-cap family engine? What would break?**
**Partly yes — and it should, for the confluence piece specifically.** The
tractable, high-value merge is P3's port: replace `confluence_breadth`'s
active-dimension/`num_edges` input with the smallcap **independent-family count**
(collapse all `*_squeeze` to one family +0.25 per extra TF, cap 1.5). That changes
ONE subscore's input, keeps the A–F output, and directly attacks the −0.398.

**What breaks on a FULL merge (one engine for both books):**
1. **Different outputs** — A–F *grade* vs 0–10 *trigger score*. A grade is not a
   selector; you'd have to pick one scale and re-teach every consumer (Track Record
   colors, `/api/log/algo`, the smallcap page all read different fields).
2. **Different family sets** — swing's 5 capped dims vs smallcap's 9 families;
   they overlap (~structure/momentum/volume/rel-strength ↔ structure/trend/volume/
   sector) but fundamental/catalyst/insider/float are smallcap-only, and swing's
   entry_discipline/stop_at_structure/rr_quality have no smallcap analog.
3. **BUG-5 would follow** — you'd need the "available-only denominator" fix in both
   or the swing grader inherits the empty-ceiling problem.
4. **Missing-data semantics differ** (see 1.5) — swing fills neutral, smallcap
   zeroes. Unifying that IS the correct end state but is the actual work.
**Verdict:** port the family-count into `confluence_breadth` now (P3, low risk);
treat full unification as a real project, not a refactor.

---

## 1.3 — Feature ledger (Addenda 1–7 + NORTH_STAR)

| Feature | Status |
|---|---|
| 4 scanner engines (swing/short/coiling/downside) + 5-dim scoring | BUILT & LIVE |
| Process grader (A–F, archetype-aware) | BUILT & LIVE |
| Retro-grades + quadrants (legacy) | BUILT & LIVE |
| r_multiple / MAE / MFE / exit_reason backfills | BUILT & LIVE |
| Track Record page + sort/filter/stat cards | BUILT & LIVE |
| MTF coherence + weekly bias panel (`mtf_bias`) | BUILT & LIVE |
| Market regime (risk_on/off/chop/**unknown**) | BUILT & LIVE (unknown added P1) |
| Market Bias strip (`bias_strip`) | BUILT & LIVE — **but the P1 surface, see 1.6** |
| News cache (Finnhub market/company/earnings) | BUILT & LIVE |
| Market Context news+earnings → Finnhub | BUILT & LIVE |
| News clustering (Addendum 7) | **BUILT backend, NOT deployed to UI** (no frontend) |
| Insider family (open-market 'P', cluster) | BUILT & LIVE (P2 units fixed) |
| Small-cap universe + 6 lanes + multi-edge scoring | BUILT & LIVE — **but empties out (BUG-5)** |
| Small-cap page + lane record | BUILT & LIVE |
| Price tiers (special/low/sub2/deep) + deep cage | BUILT & LIVE |
| Deathwatch (reverse-split/dilution/sub-$1) | BUILT & LIVE — **BUG-8 too harsh** |
| Sector trickle-down (heat + sector_early) | BUILT & LIVE |
| Hold bands (overnight/short/medium/position) | **PARTIAL** — band assigned+stored; ATR sizing / weekly signals / by-band stats NOT built |
| Catalyst events + reactivity gate (Addendum 5) | SPECCED, NOT BUILT |
| Mag7/index briefing cards (5b) | SPECCED, NOT BUILT (BUG-3 says they must exist as context-only) |
| Thesis notes JSON, learnings.json (Phase 6) | SPECCED, NOT BUILT |
| Free-roll / FREE POSITIONS panel | SPECCED (NORTH_STAR §5), NOT BUILT |
| Shadow tracking | SPECCED, NOT BUILT |
| Sector Relation Engine (lead-lag/sympathy/bottleneck) | SPECCED (NORTH_STAR §3), NOT BUILT — **Phase A priority 1** |
| Options / LEAPS / IV rank | SPECCED, NOT BUILT (Special lane's `options_liquid` hard-req is unmet → Special is dead) |
| Asymmetry lane | SPECCED, NOT BUILT |
| TF stacks per trade type + alignment score | SPECCED (NORTH_STAR §2), NOT BUILT |
| Runner / HailMary lanes | BUILT & LIVE — **NORTH_STAR/A4 says DELETE (fold into Breakout/Emerging Strength)** |
| Four daily views (night/open/lunch/close) | SPECCED, NOT BUILT |

---

## 1.4 — FUNCTION MAP (what each thing actually does, for a trader)

Scoring / selection:
- `process_grader.grade` — grades a swing setup's *discipline* A–F (did you wait at
  the pivot, is the stop at structure, R:R, timeframe agreement). **Affects:** the
  algo book grade + Track Record color. **Live.**
- `smallcap_lanes.evaluate_all` / `compute_families` — scores a cheap name 0–10 from
  9 edge families, fires ≥3-family triggers. **Affects:** the /smallcaps page + which
  small-cap paper trades open. **Live but usually returns nothing (BUG-5).**
- `smallcap_lanes._penalties` — offering/delisting/insider-selling drag the composite.
  **Live.**
- `technical_analyzer.analyze*` — the main scanner's per-name read (5 dims, archetype,
  entry/stop/target, R:R). **Feeds** the grader + proposals. **Live.**

Bias / regime:
- `mtf_bias.tf_bias` — weekly 2-of-3 trend vote (price vs 20EMA + slope + HH/HL);
  now returns `unknown` on missing data. **Feeds** the Weekly Bias panel + regime +
  smallcap sector family. **Live.**
- `bias_strip._structural` — daily conditional bias ("bullish above X"); **"Neutral"
  when not cleanly EMA-stacked AND structure neutral**, and defaults "Neutral" on
  missing data (unfixed). **Feeds** the top Market Bias strip. **This is the P1 the
  user saw. Live, misleading.**
- `mtf_bias.build_panel` — the weekly bias/RS/squeeze table for 11 SPDRs + Mag7 +
  indexes → regime. **Live.**
- `smallcap_sector.compute_sector_heat` — sector bias + RS + trigger-count → heat +
  `sector_early`. **Live.**

Enrichment / edges:
- `smallcap_edges.classify_news` — tags headlines (offering −1.5, going_concern hard
  pass, contract/FDA +1.0). **Feeds** catalyst family. **Live.**
- `smallcap_edges.insider_score` — open-market 'P' buys, cluster detection, mcap
  clamp. **Feeds** insider family. **Live (P2 fixed).**
- `smallcap_edges.revenue_trend / range52_beta` — REV ACCEL + 52w position + beta.
  **Live.**
- `smallcap_universe.build_universe` — daily screen (yfinance batch → float tier →
  Finnhub enrich). **Feeds** the whole small-cap page. **Live.**
- `news_cluster.compute_clusters` — trending-keyword clusters → tickers/sectors.
  **Feeds** `/api/news/clusters` (no UI yet). **Live backend.**
- `smallcap_signals.deathwatch_ohlc` — reverse-split hard exclusion. **BUG-8.** **Live.**

Orphaned / suspect (verify before Phase A):
- `live.py` WebSocket snapshot loop, `/api/turning-sectors` — built early, thin usage.
- Runner/HailMary lane evaluators — live but slated for deletion.

---

## 1.5 — Data source map (+ missing-data behavior)

| Field | Source | Cadence | Proxy/real | Missing-data behavior |
|---|---|---|---|---|
| Daily OHLCV | yfinance (batch, 2y) | daily build | real | name skipped |
| Splits | yfinance `actions` col | daily | real | reverse-split checks skip |
| Float / shares out | Finnhub `profile2` | 7d cache | **SO-proxy (×0.85 est)** | tier None → no lane |
| Fundamentals (margin/growth/D-E) | Finnhub `metric` | 3d | real | fundamental family = 0 ⚠ |
| Revenue trend | Finnhub `metric.series` | 3d | real | REV ACCEL absent |
| Insider txns | Finnhub `insider-transactions` | 3d | real | insider family = 0 (no penalty) |
| Filings (dilution) | Finnhub `stock/filings` | 3d | real (forms) | dilution flag off |
| Company/market news | Finnhub `company-news`/`news` | 15m/5m | real | catalyst family = 0 ⚠; panel "unavailable" |
| Earnings calendar | Finnhub `calendar/earnings` | daily | real | days-to-earnings null |
| 52w range / beta | Finnhub `metric` | 3d | real | omitted |
| Live price | Alpaca | ~5s | real | falls back to last daily close |
| Weekly bias | yfinance weekly (computed) | ~12h panel | real | now `unknown` (P1) |
| Options / IV | **NONE** (Finnhub premium, yfinance not wired) | — | — | Special lane can't fire |
| Analyst price target | Finnhub premium (403) | — | — | "unavailable" |

**⚠ MISSING-DATA-AS-FAILED-TEST (the BUG-5 class):** fundamental, catalyst, and
insider families all score **0** when the DATA is simply absent (no filings, no news
in window, market closed) — indistinguishable from "data exists, signal absent."
Because the composite divides by ALL weights, that 0 **lowers the max achievable
score**. On a quiet day the Runner lane's reachable max is ~5.4 vs a 6.5 bar → it
**cannot** trigger. This is the empty-page root cause and it recurs anywhere a family
zeroes on missing input.

---

## 1.6 — Open contradictions (listed, not resolved)

**1. P1 IS NOT CLOSED — I fixed the wrong function. Full forward trace of SPY:**
- **Layer 1 (frontend):** the dashboard's top **"Market Bias"** strip → `loadBiasStrip()`
  → **`GET /api/bias-strip`**. (A separate lower panel, "Weekly Bias & Regime," calls
  `/api/market-bias`.)
- **Layer 2 (endpoint):** `/api/bias-strip` → `bias_strip.build(ALPACA, symbols)` —
  **live compute**, not a DB table.
- **Layer 3 (cache):** in-memory `bias_strip._CACHE` per symbol, 10-min TTL, rebuilt
  from yfinance **daily** bars via `_structural()`.
- **Layer 4 (value RIGHT NOW, verified):** **SPY = "Neutral"** (price 755.1 < level
  758.45; daily structure NEUTRAL and not price>ema20>ema50). NVDA/AMZN/META/TSLA also
  "Neutral"; GOOGL "Bearish"; AAPL "Bullish".
- **Meanwhile** `/api/market-bias` (the function I "fixed") holds **SPY bullish, NVDA
  bullish, GOOGL bullish** (weekly). **The two surfaces contradict on screen.**
- **Conclusion:** my P1 change hardened `mtf_bias.tf_bias` (the weekly panel, which
  was already working). The neutral the user SAW is `bias_strip._structural` — a
  different daily/conditional engine that (a) legitimately reads "Neutral" for names
  below their trigger level, but (b) **still defaults "Neutral" on missing data**
  (line 80), and (c) **openly disagrees with the weekly panel**. **P1 stays OPEN.**
  Real fix (Phase A): make `bias_strip` distinguish `unknown` from conditional-neutral,
  and reconcile/label the two bias reads so the UI can't show SPY Neutral and SPY↑ at
  once.

**2. Threshold 6.5 is unvalidated** — tuned Sunday on a sample with the sector family
forced to 0 (no panel in the test DB) AND before the BUG-5 ceiling fix. Any trigger
count read off it is provisional.

**3. Intraday-dependent surfaces:** currently **none** of the live lanes require
intraday — the small-cap engine is daily-only, and Runner/HailMary (which A4 deletes)
used a daily rel_vol proxy, not true intraday. NORTH_STAR's Day/Overnight bands + the
"1h trigger" (BUG-4) are SPECCED and would need A0's yfinance-intraday verification
before anything emits on 1h/15m.

**4. Other two-systems disagreements:** (a) bias — bias_strip vs mtf_bias (above);
(b) edges — swing `num_edges` (anti-predictive) vs smallcap independent-family count;
(c) missing-data — neutral-fallback (swing/bias_strip) vs zero (smallcap); (d) grade
scales — A–F vs 0–10, never reconciled.

---

## 1.7 — Honest assessment (blunt)

- **Genuinely working:** the main 4-engine swing scanner + process grader + Track
  Record (78 rows, retro-grades, quadrants) is the solid core. The Finnhub news/
  earnings layer and the weekly `mtf_bias` panel are real and correct.
- **The small-cap engine is well-designed but starves itself.** The multi-edge/
  independent-family architecture is the right idea (and the fix for the swing
  grader), but BUG-5 makes the page empty most days, so nobody sees it work. It
  reads as broken even though the design is sound.
- **Theater #1: the Market Bias strip.** It shows SPY "Neutral" while the panel two
  inches below shows SPY bullish. A trader glancing at the top of the page gets a
  false "market has no bias" read. This is the most damaging single thing on the site.
- **Theater #2: Special lane + anything options.** Special requires `options_liquid`,
  which is never computed (no options module). It's a dead tab. ~50% of the user's
  actual trading (options) is entirely absent.
- **Theater #3: half-built hold bands.** Bands are tagged on trades but there's no
  ATR sizing, no weekly-breakout signal, no by-band stats — the feature looks present
  and does nothing.
- **Dead weight I'd tear out:** Runner + HailMary lanes (lottery lanes the trader
  profile rejects; A4 agrees), the WebSocket `live.py` loop / `turning-sectors` if
  unrendered, and the raw `num_edges` influence in the grader (measured
  anti-predictive).
- **The single most valuable unbuilt thing** is the Sector Relation Engine (NORTH_STAR
  §3) — it's the user's actual edge and there is literally nothing like it in the
  code. Everything else is refinement; that is the differentiator.
- **The two-scoring-systems split is the core architectural debt.** Not because two
  engines is wrong, but because they disagree on *missing data*, *edge counting*, and
  *output scale* with no reconciliation — which is exactly how a trader loses trust in
  a tool.
- **What actually reflects the trader today:** ~30%. The swing/grade/track-record spine
  fits. The sector lens, options, asymmetry hunting, free-roll, and the four daily
  rhythms — the things that make it *his* — are specced, not built.

---
**STOP. Awaiting review before Stage 2 (Phase A).** Nothing in the app was modified;
only NORTH_STAR_v2.md, PHASE_A_PROMPT.md, and this file were written to disk.
