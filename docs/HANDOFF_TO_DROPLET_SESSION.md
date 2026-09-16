# Handoff prompt — for the session that has droplet access

Paste everything below the `---` into the other Claude session verbatim.

---

## Context you need before touching anything

You're on `pabhathabusiness/autonomous-trading-system`. **The live droplet is dramatically ahead of GitHub.** On the live `pabs.trading` site, the header nav has ~19 destinations:

**Top row:** Dashboard · Trade Ideas · One Read · Market · Options · Sectors · Small Caps · Watchlist · Playbook · More
**More dropdown:** Sector Deep Analysis · Reports · Track Record · My Positions · Earnings · Top 10 Watch · Day Trades · Structure & Zones · SPY Watcher (classic)

GitHub's `main` and the branch `claude/ssh-key-access-check-t58nou` only know about **4 nav tabs**: Dashboard, Sectors, Track Record, More.

**The droplet has never been pushed back to Git.** Every UI change on the live site exists in the droplet checkout only. If anyone deploys current GitHub to the droplet, most of the live UI gets wiped.

There's also a commit `343cadd` on `claude/ssh-key-access-check-t58nou` that swaps two nav tabs in the stale index.html. **Do not deploy that commit.** Revert it before doing anything else so the branch can't accidentally reach the droplet:

```bash
git fetch origin claude/ssh-key-access-check-t58nou
git checkout claude/ssh-key-access-check-t58nou
git revert 343cadd --no-edit
git push
```

## Frozen inputs on `claude/ssh-key-access-check-t58nou`

Design docs I built during the wait. Treat as inputs — reconcile against them, do NOT rewrite them:

- `PLAYBOOK_v2.1.1.md` — 14 owner-ratified rules (D-1..D-14). Options-first two-layer decisions (underlying setup + option expression). R = account loss from option position; invalidation = level on underlying. Hard blocks: <2R, >2 concurrent, MIXED regime.
- `docs/TOP10_UX_SPEC.md` — three-band Top 10 page (regime / guardrails / ideas). § 14 lists the reconciliation checklist.
- `docs/MARKET_INTELLIGENCE_SCHEMA.md` — `/api/market/intel` contract (regime / breadth / vol / correlation). § 10 lists reconciliation checklist.
- `docs/TRADE_CARD_COMPONENT.md` — TradeCard spec with all 14 owner-specified fields; FSM DETECTED/FORMING/READY/TRIGGERED/BLOCKED/EXPIRED; `current_structure_bias` explicitly independent of `setup_hypothesis`; `conditional_trade_side` as `{ long_trigger?, short_trigger?, resolved_side? }`.
- `docs/prototypes/trade_card.html` — self-contained HTML prototype (4 example cards, legend, FSM diagram).
- `docs/SCANNER_TO_TOP10_PIPELINE.md` — FSM for `detected → forming → ready → triggered` (+ BLOCKED, EXPIRED); existing ranker preserved as black-box.
- `research/schwab_*.py`, `research/results/*.md` — evidence base (Schwab CSV + preregistered SPY/correlation reports).

## Your job, in strict order

### Step 1 — Sync the droplet source to GitHub FIRST

Nothing proceeds until the live `src/` is in Git. On the droplet:

```bash
cd <droplet checkout dir>
git status                                       # confirm drift exists locally
git checkout -b sync/live-droplet-$(date +%Y-%m-%d)
# stage UI first, then anything else that drifted
git add src/
git status                                       # verify no .env / secrets / DB files staged
git commit -m "sync: live droplet source (drift from main)"
git push -u origin sync/live-droplet-$(date +%Y-%m-%d)
```

**Constraints:**
- Do NOT `git reset --hard`, rebase, or force-push against the droplet — that would destroy the state you're capturing.
- Add secrets / `.env` / SQLite DBs to `.gitignore` **before** `git add`; verify with `git status`.
- Do NOT merge to `main` yet. Open a PR from `sync/live-droplet-<date>` → `main`. The PR diff **is the recovery** — it needs to be reviewed intact.

### Step 2 — Reconciliation audit

Once the sync PR exists, produce `docs/RECONCILIATION_AUDIT.md`. For each of the 6 spec docs, one section answering:

- Does the live UI already do what the spec describes? (yes / partial / no)
- Specific gaps.
- Places where the live UI has functionality the spec **doesn't mention**. Do NOT delete these — extend the spec instead.

Focus areas from the live nav that are certainly absent from the specs and must be preserved:
- Trade Ideas (whatever it currently does)
- Small Caps
- Sector Deep Analysis
- SPY Watcher (classic)
- My Positions
- Structure & Zones
- Day Trades
- Earnings

### Step 3 — Propose smallest vertical slice

The owner has directed exactly one slice for the first implementation:

```
existing scanner candidate
  → FSM state
  → trade-card data contract
  → Playbook context
  → rendered live Trade Card
```

Constraints on this slice:
- Do NOT modify ranking logic.
- Do NOT modify trading logic.
- Do NOT redesign Top 10 concurrently.
- Do NOT fan out across multiple scanner types.
- One scanner type, one card, live.

**STOP after the proposal.** Write it as `docs/VERTICAL_SLICE_PROPOSAL.md` with the exact file diffs (as a plan, not applied). Wait for the owner's go-ahead before writing implementation code.

### Step 4 — Nav reorder (only after 1–3 land)

Owner's target nav order:

```
Dashboard | Market | Scanner | Top 10 | One Read | Options | Sectors | Playbook | Watchlist | Research | More
```

Live current order:

```
Dashboard | Trade Ideas | One Read | Market | Options | Sectors | Small Caps | Watchlist | Playbook | More
```

Mapping decisions (owner-facing questions to raise, not answer unilaterally):

- Is "Scanner" a new tab or a rename of "Trade Ideas"?
- Is "Research" a new tab or the move-out of items from More?
- Where do Small Caps / Sector Deep Analysis / SPY Watcher / etc. land in the target IA? (Currently: Small Caps top-level, others in More.)

Only reorder after these are answered. Do not delete tabs the live site has.

## Non-goals (do not do)

- No deploy until reconciliation audit is done AND vertical-slice proposal is approved.
- No stubs, no "Coming Soon" tabs, no fabricated routes.
- No wiring of playbook rules (D-1..D-14) into production during the first slice.
- No rewrite of any of the 6 frozen spec docs.

## First message to send back to the owner

After Step 1 completes (sync PR open), reply with:

- The sync PR URL.
- The list of files that drifted (`git diff --name-only main..sync/live-droplet-<date>`).
- Any secrets/DBs you had to `.gitignore` during the sync.
- A one-line question if `src/static/index.html` diverged in ways that suggest the app.js routing also diverged.

Then start Step 2.
