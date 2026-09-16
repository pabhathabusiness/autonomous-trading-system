# Top 10 — UX Specification (DRAFT)

**Status:** DRAFT for owner review — NOT wired to production. Written against
the playbook framework in `PLAYBOOK_v2.1.1.md`. To be reconciled against the
actual live droplet implementation (page + `/api/top10/ideas`) once the
droplet checkout is synced back to GitHub.

**Scope:** describes what the Top 10 page *should present*, how each idea
card *should read*, what filters/interactions belong to it, and which
playbook rules gate an idea's appearance. Does not describe ranking model
internals beyond the inputs the card must expose to the owner.

**Non-goals of this doc:**

- Does not specify the ranking algorithm (that is a separate research
  question — see § 5 "Ranking inputs" below for the required surface area).
- Does not specify backend routes, DB schemas, or job cadence.
- Does not modify any existing frontend file.

---

## 1. Purpose

The Top 10 page is the **single daily entry point** for the owner to decide
what to trade today. It answers three questions in order:

1. **What is the current market regime, and does it permit new risk?**
2. **What are the strongest 10 ideas that survive every HARD SAFETY rule
   and the current regime filter?**
3. **For each idea: what is the exact setup, invalidation, option
   expression, and R?**

If the owner cannot answer those three questions from this page alone
without opening another tab, the page has failed.

## 2. Placement in the app

Top 10 is a **first-class nav destination**, not a section under Dashboard.
Target nav order (per prior IA discussion, subject to droplet sync):

`Dashboard | Market | Scanner | Top 10 | One Read | Options | Sectors | Playbook | Watchlist | Research | More`

Top 10 sits after Scanner because Scanner is the *raw* candidate pool and
Top 10 is the *curated + rule-gated* subset.

## 3. Page layout

Three stacked bands, top to bottom, on both desktop and mobile:

### 3.1 Regime band (top, fixed height)

Full-width bar. Must show, at a glance:

- **SPY classification** (BULLISH / BEARISH / MIXED / UNKNOWN) as a
  colored chip. MIXED is the critical case per `schwab_mixed_correlation_report.md`
  and must read as a warning, not a neutral state.
- **Effective bet count** (from `schwab_hypothesis_spy_load.py`): current
  open positions, collapsed by correlation cluster. E.g. "3 positions,
  effective ≈ 2 clusters."
- **Portfolio load state**: NORMAL / STRETCHED / OVERLOADED per playbook
  D-2 (max 2 concurrent positions).
- **Timestamp of the classification** (regime was computed at HH:MM UTC).

If any of these are stale (> 1 trading hour old), the whole band is
rendered muted and shows "Refresh required" instead of numbers. Do not
show stale numbers as if current.

### 3.2 Guardrail band (mid, collapsible)

Renders the 4-5 gating rules that produced *today's* Top 10. Each rule
shows its state:

- **HS-A (MIXED-regime block):** OK / TRIGGERED
- **HS-B (Portfolio load ≥ 2):** OK / TRIGGERED
- **HS-C (Cooldown after loss cascade, D-9):** OK / TRIGGERED
- **HS-D (Weekly refresh scope, D-12):** OK / STALE
- **HS-E (<2R hard block, D-13):** applies per-card

When TRIGGERED, the band explains in one sentence what the owner
needs to do (e.g. "MIXED regime — new full-size entries paused; only
scaled-in adds to existing GREEN cards are eligible").

### 3.3 Ideas band (main, scrollable)

Ten card slots. If fewer than 10 ideas survive the gates, show the
survivors and a **transparency slot** at the end reading:

> "Only N ideas cleared all gates today. See § 7 Empty states."

Never pad with weaker ideas to reach 10.

## 4. Idea card — required content

Each card is a compact block that fits the playbook trade-card format
(PLAYBOOK v2.1.1 § 15). Fields, top to bottom:

### 4.1 Header row

- **Ticker** (large, monospace).
- **Direction chip**: LONG / SHORT.
- **Evidence status chip**: SUPPORTED_SAMPLE / PROVISIONAL /
  INSUFFICIENT_SAMPLE / NEGATIVE_SAMPLE (per PLAYBOOK v2.1 § 12). Color
  scale runs green → yellow → gray → red; NEGATIVE_SAMPLE tickers should
  not appear in Top 10 at all except in a deliberate "watch" state — see
  § 6 filters.
- **Rank badge**: "#1" through "#10". Rank is deterministic for the day;
  cards do not reshuffle without a page refresh.

### 4.2 Setup block (underlying layer)

Per playbook two-layer framework:

- **Setup name** (one line, e.g. "Reclaim + retest of 20-DMA on
  intraday").
- **Invalidation level**: the specific price on the underlying that
  kills the thesis. Not the option price. This is where the owner's R
  is measured from at the *setup* level.
- **Confirmation trigger** (optional): the condition that would move the
  card from WATCH to ENTRY-READY (e.g. "break above $184.20 on ≥ 1× 20-day
  average volume").

### 4.3 Option expression block (option layer)

- **Suggested strike / expiry** — display but do not auto-execute.
- **Estimated option price** at current underlying and IV, via the
  D-11 estimator. If the estimator is stale or has failed, the block
  reads "estimator unavailable" and the card is flagged with a subtle
  "manual price check required" tag.
- **Contracts** (default 1 per D-3).
- **Account risk in $**: contracts × option price × 100.
- **R multiple to invalidation**: how much of that $ is at risk if the
  underlying hits invalidation, per the D-11 estimator's revalue at
  invalidation.

### 4.4 R block

- **Planned R** (net expected R at target vs risk at invalidation).
  Must be ≥ 2R or the card is blocked from ENTRY-READY per D-13; a
  card that is < 2R may still appear in the list but with a red "R <
  2R — blocked" strap and no BUY button.
- **Owner override link** (per D-13's owner-override protocol) — opens
  a modal that logs the override to the skipped-opportunity log
  (D-14) with reason text.

### 4.5 Correlation / cluster tag

- **Cluster label** (e.g. "Semi mega-cap long", "Index long"). Cards in
  the same cluster as an already-open position show a "would exceed
  effective bet cap" strap and are visually de-emphasized.

### 4.6 Actions

Three actions, no more:

1. **Preview trade** — opens the option-order preview modal (reuses
   existing `preview_option_order` MCP surface); does not submit.
2. **Add to watchlist** — non-committing, tags the ticker for the
   day.
3. **Dismiss for today** — records to the skipped-opportunity log
   (D-14) with a required reason from a small enum: "wrong regime" |
   "R too low" | "correlation" | "conviction" | "other". Free-text
   optional.

The card does **not** contain a one-click BUY button. All entries
route through the Preview → confirm flow.

## 5. Ranking inputs — what the card must expose

The UX spec does not specify the ranking algorithm, but it constrains
what the algorithm's output must expose so the card can render honestly:

Required fields per idea, from `/api/top10/ideas` (aspirational contract):

| Field | Type | Source |
|---|---|---|
| ticker | string | scanner |
| direction | enum(LONG,SHORT) | scanner |
| evidence_status | enum | ticker-evidence table |
| setup_name | string | scanner rule name |
| invalidation_px | float | scanner rule |
| confirmation_trigger | string? | scanner rule |
| suggested_strike | float | option-picker |
| suggested_expiry | date | option-picker |
| est_option_px | float? | D-11 estimator |
| est_at_invalidation_px | float? | D-11 estimator revalued |
| contracts_default | int | D-3 (1) |
| cluster_label | string | correlation-cluster classifier |
| regime_at_computation | enum | SPY classifier |
| refresh_ts | iso8601 | job |

If the estimator or classifier is unavailable, the field is `null` and
the card renders the "unavailable" state — never a fabricated value.

## 6. Filters

Right-hand or top filter strip (all default OFF unless noted):

- **Direction**: LONG / SHORT / both (default both).
- **Evidence**: default hides NEGATIVE_SAMPLE. Toggle to show them for
  audit purposes only, with a red strap on every visible card.
- **Cluster**: hide ideas in already-open clusters (default ON in
  STRETCHED or OVERLOADED load state; OFF otherwise).
- **R minimum**: default 2.0 per D-13. User can drop this but the app
  logs the change to the D-14 skipped-opportunity log.

Filter state is per-session, not persisted across days.

## 7. Empty states

Distinct copy per cause. Never blank; always tell the owner *why*:

- **Fewer than 10 ideas survived gates:** "N ideas cleared all gates
  today. This is expected in <regime>; padding is disabled."
- **MIXED regime, all cards blocked:** "SPY is MIXED. New full-size
  entries paused per playbook § 5. Add-only cards below, if any."
- **Cooldown active (D-9 loss cascade):** "Cooldown active until
  <date>. Top 10 is disabled per rebuild-phase re-review triggers
  (PLAYBOOK v2.1.1 § 21)."
- **Estimator down:** "Option-value estimator is unavailable. Top 10 is
  showing setups only — no option expression. Do not auto-size."
- **Scanner stale:** "Scanner last ran <hh:mm ago>. Top 10 is stale.
  Refresh manually or wait for the next refresh window."

## 8. Refresh cadence

- **Regime band:** every 5 minutes during regular trading hours, else
  every 30 minutes.
- **Guardrail band:** on every regime refresh + every fill/close
  webhook.
- **Ideas band:** twice daily by default (per D-12 weekly refresh
  scope — the *composition* of the Top 10 refreshes on the D-12
  cadence; only the *prices and estimator outputs* on cards refresh
  intraday). Manual "recompute" button available with a 30-second
  minimum cooldown to prevent thrash.

The refresh cadence is deliberately conservative to match D-12. Faster
churn would encourage overtrading — an explicit anti-goal.

## 9. Persistence and determinism

- The exact list ranked #1-#10 for a given (date, regime, effective
  bet count) tuple must be reproducible from the underlying scanner
  and rules — no random tie-breaking. Tie-break on
  `(evidence_status_rank, cluster_diversity, ticker alphabetical)`.
- Dismissals for a given day persist to end-of-day; they do not carry
  over.
- Watchlist adds persist normally.

## 10. Instrumentation (owner-facing, not just analytics)

Every card impression + action must land in the skipped-opportunity
log (D-14) when relevant, because the *skipped* trades are as
diagnostic as the taken ones. Fields per D-14:

- date/time
- ticker
- setup
- suggested option
- estimated R
- action taken (dismissed / previewed / traded / watchlisted)
- reason
- regime + cluster load at the moment of decision

These are already spec'd in PLAYBOOK v2.1.1 D-14; this section is a
reminder that Top 10 is the primary write-site.

## 11. Accessibility

- All chips must have text labels, not just color. NEGATIVE_SAMPLE red
  and BULLISH green must be distinguishable to a colorblind reader.
- Card is keyboard-navigable end-to-end. `Enter` opens Preview; `d`
  opens the Dismiss modal.
- No card auto-focuses on load; the owner picks.

## 12. What Top 10 is NOT

To keep this page from silently drifting into "the app's opinion
about what to trade":

- Not a Buy button. Every action funnels through Preview.
- Not a leaderboard. Rank #1 does not mean "trade this"; it means
  "highest evidence + regime fit *survivor of the gates*."
- Not a live P&L. Open positions belong on Dashboard.
- Not a news feed. News belongs on One Read.
- Not a screener. Raw candidates belong on Scanner.

If the page starts accruing responsibilities from that list, split
them back out.

## 13. Open questions for owner

Marked so the eventual real implementation can resolve them:

1. **Should NEGATIVE_SAMPLE tickers ever appear in Top 10 with a red
   strap, or be hidden entirely?** — default here is "hidden unless
   toggled."
2. **Should the Top 10 include shorts as first-class in BULLISH
   regime, or only in BEARISH/MIXED?** — default here is symmetric.
3. **Is Preview the sole entry surface, or should there be a
   "one-tap paper-trade" for research capture?** — default here is
   Preview only.
4. **Where does the "why this ticker is #N" explanation live?** — a
   modal on card expand, or an inline expandable panel? Default:
   inline expandable so the owner does not lose context.

## 14. Reconciliation checklist (post droplet sync)

Once the live droplet checkout is pushed and merged, reconcile this
spec against reality by answering:

1. What does the live `/api/top10/ideas` response actually return? Map
   each field to the § 5 table.
2. Does the live page have a regime band? If yes, does it show what
   § 3.1 requires? If no, add it.
3. Does the live page block cards on R < 2R (D-13)? If no, add the
   block.
4. Does the live page log skipped opportunities (D-14)? If no, wire
   the write.
5. Which of § 13's open questions has the live implementation already
   answered — implicitly or explicitly?

The output of that reconciliation is the actual redesign work.

---

**Related docs:**

- `PLAYBOOK_v2.1.1.md` — governing rules (D-1 through D-14)
- `research/results/schwab_hypothesis_spy_load_report.md` — evidence
  for regime band + effective bet count
- `research/results/schwab_mixed_correlation_report.md` — evidence
  for MIXED-regime warning and correlation cluster tagging
- `research/results/schwab_diagnostic_report.md` — evidence for the
  R ≥ 2R hard block (D-13)
