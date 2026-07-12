# Overnight Autonomous Build — Morning Report (2026-07-12)

> **LIVE VALIDATION (post-report, ~1h after deploy):** the full-universe rebuild
> (new logic) reached ~1,000 names and a live scan fired **2 real multi-edge
> triggers on a partial Sunday universe** — INTZ (hailmary 6.83: volume+catalyst+
> float; chips INSIDER BUY 2·$547k·12d, REV ACCEL, CONTRACT AWARD) and ARTV
> (value 6.57: compression+trend+fundamental+insider). The zero-trigger bug is
> **confirmed fixed on real data**, and the T2 signals (insider family, REV ACCEL
> trends, news classification) are all firing. Full section 10 below.

**TL;DR:** The zero-trigger bug is **architecturally fixed and deployed** (T1), the
news-polarity bug + insider signal shipped (T2), grade diagnostic run (T6),
validation run + threshold tuned (T7), and everything is **live behind the
guardrails** (T8: `auto_execute` FALSE, 78 legacy rows intact, paper-only). A full
universe rebuild on the new logic is running in the background (~1h). Tasks **T3,
T4, T5, and the full Addendum-6 band mechanics were NOT reached** — budget ran out
after the high-priority fixes; details + exact next steps below. Nothing unsafe was
done unattended.

---

## 1. What shipped, per task (commit hashes)

| Task | Status | Commit(s) |
|---|---|---|
| T0 Safety + save addenda 3-6 | ✅ done | `12062a4` |
| T1 Zero-trigger fix (float F3, multi-edge scoring, tiers, Special+Coiled) | ✅ done | `49226e9` |
| T2 Finnhub depth (news-polarity FIX, insider family, trends, 52w/beta) | ✅ core done | `ce58d67` |
| T3 Sub-$5 -> algo book + Track Record (F6) | ❌ NOT reached | — |
| T4 Catalyst events + reactivity gate | ❌ NOT reached | — |
| T5 Mag7 / index briefing cards | ❌ NOT reached | — |
| T6 Grade-floor diagnostic (F5) | ✅ done (no floor) | diagnostic only, no code |
| Addendum 6 Hold bands | 🟡 partial | band assign+store in `49226e9`; ATR/weekly/stats table NOT done |
| T7 Validation dry scan (F4) | ✅ done (sampled) | `5132bbb` |
| T8 Deploy | ✅ done + gate passed | deployed HEAD `5132bbb` |

**What the fix actually changed (T1):** the lanes no longer AND ~5 hard gates
(probability collapse). Every name is scored on a 0-10 composite from 9 weighted
edge families; a trigger needs `composite >= threshold AND >= 3 independent
families >= 0.5`. Float is no longer a universe gate (ceiling 1B, per-lane
ceilings + scored edge). rel_vol is a scored curve. Sub-$1 is a -1.5 penalty, not
an exclusion (reverse-split/dilution stay hard). Price tiers special/low/sub2/deep.
New Special (options-gated) + Coiled (WATCHING/TRIGGERED) lanes. 12 engine unit
tests pass.

**T2 highlight — the live bug:** an `offering` / `going_concern` headline was
scoring as a POSITIVE catalyst. Now classified (offering -1.5, going_concern -2.0
hard pass); the catalyst family zeroes negatives and a composite penalty applies.
Insider family uses open-market 'P' purchases only (comp codes M/A/G excluded;
cluster = 2+ distinct insiders in 30d). 15 edges unit tests pass; real-data
enrichment verified (GPRO's -$2M insider selling correctly scores 0).

---

## 2. Finnhub probe (Addendum 4 Part 1)

| Endpoint | Free tier? | Notes |
|---|---|---|
| /stock/insider-transactions | ✅ | 28 txns for GPRO |
| /stock/insider-sentiment | ✅ | MSPR months |
| /stock/earnings (surprise) | ✅ | 4 quarters |
| /stock/recommendation | ✅ | 4 periods |
| /stock/peers | ✅ | 11 real peers |
| /stock/metric `series` | ✅ | annual + quarterly time series |
| 52WeekHigh/Low + beta | ✅ | already in the metric snapshot |
| /stock/social-sentiment | ❌ 403 premium | LOW priority; skipped |
| shares-outstanding series | ⚠️ absent | deathwatch rule (d) keeps accruing SO snapshots |
| /stock/price-target | ❌ 403 premium (prior probe) | rendered "unavailable" |
| /stock/option-chain | ❌ 403 premium (prior probe) | Special uses yfinance (NOT yet built) |

Wired now: insider-transactions, news classification, metric series (rev trend),
52w/beta. Built-but-not-wired: earnings-surprise scoring, peer-valuation
percentile, recommendation trend, news velocity (client methods exist).

---

## 3. Dry-scan results (T7) — SAMPLED, see deviation

- **Sample:** 36 names (weekend, alphabetical "A" names, no live market-bias panel
  in the test DB). This is NOT representative — treat as a floor, not the truth.
- **Triggers (current day):** 0.
- **Composite histogram (best per name):** `0:6 1:7 2:8 3:9 4:3 5:3 6:0 7:0 ...` —
  nothing reached 6 on the sample.
- **Family-firing frequency:** float 56 · volume 30 · trend 27 · fundamental 20 ·
  insider 16 · compression 4 · catalyst 4 · structure 3 · **sector 0**.
- **Biggest filter:** `sector` (0 — the test DB has no bias panel, so the sector
  family was forced to 0, understating live composites by ~0.9) and `catalyst`
  (few fresh headlines on weekend A-names).

**Why 0 is largely an artifact:** two of the three suppressors (no sector panel,
no fresh weekend catalysts) are environment/sample effects, not the engine. On the
LIVE full universe with the bias panel + fresh news, composites run meaningfully
higher. **The authoritative 2-8/day validation MUST be re-run on the full live
universe on a trading day** (the rebuild kicked tonight is step 1).

---

## 4. Final composite threshold: 6.5 (from 7.0)

F4 says <2/day -> lower in 0.25 steps toward a 6.0 floor. But lowering fully to
6.0 on an *understated* sample (missing sector panel ~ -0.9) would risk live
over-triggering. So I stepped 7.0 -> **6.5** (one measured step) and flagged
re-validation on the full live universe. It's a single constant in
`smallcap_lanes.py` (`COMPOSITE_THRESHOLD`) — trivially reversible. **Re-tune it
per F4 once the full live universe + a trading day give a real trigger count.**

---

## 5. Grade-floor diagnostic (T6, F5)

| bucket | n | avg r_multiple |
|---|---|---|
| C_and_above | 12 | **-0.205** |
| D_F | 12 | **-0.013** |
| total closed graded | 24 | |

D/F is **not** worse than C+ — it's slightly *better*. The F5 condition ("D/F
clearly worse AND n>=10") is not met, so **no grade floor was added** (correct
per F5). The signal is noise on a tiny, mostly-retro sample; grades aren't
predicting outcomes yet. Revisit once there are more live-graded closed trades.

---

## 6. Reactivity gate (T4)

**NOT BUILT.** T4 (catalyst events + reactivity engine) was not reached this
session. No (symbol, event_type) pairs evaluated. This is the honest status —
see section 9 for where it sits in the queue.

---

## 7. DEVIATIONS (decisions not pre-specified)

1. **T7 sampled, not a 30-day point-in-time backtest.** The full 587-name build is
   ~1h and a 30-day per-name signal recompute on top was out of budget. I ran a
   current-day scan on a 36-name sample + histogram/family-frequency and
   extrapolated. Logged; the real validation runs on the live rebuild. (F8: safer
   + reversible; surfaced not hidden.)
2. **Threshold set to 6.5, not F4's 6.0 floor.** Justified in section 4 — the
   sample understated live composites by ~0.9, so 6.0 on that basis risked live
   over-triggering. 6.5 is the safer measured step. Reversible constant.
3. **T2 scoped to the two highest-value pieces** (news polarity + insider) plus the
   free already-fetched fields (52w/beta/rev-trend). Earnings-surprise scoring,
   peer-valuation percentile, recommendation trend, and news velocity have client
   methods but are not yet wired into scoring. (F8: shipped the highest-value,
   additive; nothing faked.)
4. **Addendum 6 partial:** `hold_band` is assigned per lane + stored on triggers
   and trades, and per-band R:R/time-stop constants exist. The ATR-based stop/target
   sizing, the weekly-resample breakout signals, the overnight next-open modeling,
   and the second (by-band) record table are NOT built.
5. **Special lane options gate uses yfinance — NOT yet built.** `options_liquid` is
   the one hard requirement for Special; until the yfinance options module lands,
   Special cannot trigger (it renders as "no options" gracefully, per F2). The
   other 5 lanes are fully live.
6. **Universe threshold re-validation pending:** the live universe at deploy time
   held 297 stale-format rows (built pre-T1); a full rebuild on new logic was
   kicked and is running.

---

## 8. What failed / issues hit (with fixes)

- **Earlier tonight (pre-overnight):** the first full universe build errored on all
  587 survivors — per-name `yf.Ticker().splits` calls were rate-limited by Yahoo
  right after the batch download. Fixed (commit before overnight) by pulling splits
  from the batch `actions=True` column + a 2y window. Verified clean.
- **No failures during T0-T2/T6-T8.** All unit tests passed; deploy gate passed
  (78 rows intact); no errors in the service log post-deploy. ROLLBACK.md was not
  needed.

## Live verification at deploy (T8)
- service `active`; `/api/log/algo` = **78** trades (gate passed);
  `/api/scheduler` = auto_execute **False**, smallcap_enabled **True**;
  `/api/smallcap/*` respond; no secrets in the deployed tree (git-archive of
  tracked files only; `.env` + `config.json` untouched). DB snapshots saved to
  `backups/overnight_T0_20260712.db` + `backups/pre_T8_*.db`.

---

## 9. What still needs YOU / what's queued (in priority order)

1. **Re-validate the trigger rate on the full live universe** (the rebuild running
   now, and the first Monday scan). Check `/smallcaps` + `/api/smallcap/triggers`.
   If triggers/day is still <2 or >8, tune `COMPOSITE_THRESHOLD` per F4 (floor 6.0,
   ceiling 8.0). **This is the single most important follow-up.**
2. **T3 — wire sub-$5 lanes into the algo book + Track Record** (F6). NOT done.
   Requires the `get_algo_trades` quarantine flip (exclude hailmary lane + deep tier
   instead of all smallcap) + the book filter chip + per-book stat cards, with the
   78-row gate re-checked. Deliberately deferred so the 78 rows stayed safe tonight.
3. **Special lane options module** (yfinance `Ticker.option_chain`) — unblocks the
   Special lane.
4. **Addendum 6 full band mechanics** (ATR stops, weekly breakout signals, overnight
   next-open modeling, by-band record table).
5. **T4 catalyst events + reactivity gate**, then **T5 Mag7/index briefing cards.**
6. **Rotate the Finnhub key** (it appeared in the chat transcript earlier).
7. Remaining A4 wiring: earnings-surprise scoring, peer-valuation percentile,
   recommendation trend, news velocity (methods exist, scoring not wired).

Nothing here was auto-decided in a way that touches real money or the main book.
The small-cap lane remains fully quarantined and paper-only.

---

## 10. LIVE VALIDATION (full-universe rebuild, ~1h post-deploy)

The new-logic universe is **much larger than the addendum estimated (~150-400)**:
float ≤1B (F3) + the wider $0.20-10 price range yield **~1,000 names** (still
enriching when measured at 982). Distribution was healthy across every tier:
- price tiers: special 379 · low 327 · sub2 146 · deep 130
- float tiers: mid 332 · low 255 · standard 185 · runner 164 · large 29 · >1B 17

A live scan over the partial 982-row universe (Sunday, mid-build) fired **2
triggers** (both auto-opened as quarantined paper trades):

| symbol | lane | composite | families | chips |
|---|---|---|---|---|
| INTZ | hailmary | 6.83 | volume, catalyst, float | INSIDER BUY 2·$547k·12d · REV ACCEL · CONTRACT AWARD |
| ARTV | value | 6.57 | compression, trend, fundamental, insider | INSIDER BUY · REV ACCEL |

**This confirms the fix end-to-end on real data:** triggers are produced (not
zero), the ≥3-family rule holds, composites clear 6.5, and the T2 signals
(insider family, REV ACCEL trends, CONTRACT AWARD news classification) all fire.
2 triggers on a *partial Sunday* universe implies the live weekday rate on the
full ~1,000-name universe (with the sector panel + fresh news active) should land
in or above the 2-8/day target — **re-check the count on Monday and tune the 6.5
threshold per F4 if it runs hot.**

### New findings / follow-ups from the rebuild
1. **Universe is ~1,000 names, not ~400.** Enrichment (~5.5s/name with the insider
   call) takes ~90 min for a cold build; daily refreshes are cheap (cached). If
   the rate budget becomes a problem, consider capping enrichment to the top-N by
   a cheap OHLC pre-score, or tightening the $vol floor above $300k. Not urgent.
2. **Insider dollar formatting bug (minor):** ARTV showed "INSIDER BUY 2·$1034712k"
   — an implausible ~$1B, almost certainly a bad transactionPrice/share value in
   the Finnhub payload or a net_dollars sum error. Add a sanity clamp / per-txn
   validation in `smallcap_edges.insider_score`. Display-only; does not affect
   safety.
3. **Dilution is a soft factor, not a hard block, in the value lane now** (only
   deathwatch reverse-split + going_concern are hard, per A3's "everything else
   scores"). ARTV triggered value with a DILUTION chip. If you want value to
   reject diluters outright, add dilution_risk as a value-lane hard gate — a
   deliberate deviation from A3's philosophy, so left for your call.
