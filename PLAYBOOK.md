# TRADING PLAYBOOK — personal operating rules

This is a personal rules document, not a program. Every rule is tied to
numbers from your own Schwab realized-gain/loss export.

- **Analysis window**: 06/16/2026 → 09/16/2026 (3 months, 63 trading days).
- **Analyzer**: `research/schwab_feedback.py` — re-run any Schwab CSV export
  through it to refresh these numbers.
- **PABS ≠ Schwab.** PABS (this repo) is a research and decision-support
  system. Schwab is the actual brokerage account. This playbook governs
  what YOU do in Schwab, and gets updated as PABS's setup-context layer
  and the Schwab feedback loop produce evidence.

---

## Bottom-line audit (evidence, not opinion)

| Metric | Value |
|---|---|
| Account: beginning value | $3,166.67 |
| Contributions this period | +$2,035.00 |
| Investment gain/loss | −$4,249.07 |
| Ending value | $952.60 |
| **Cumulative return** | **−87.72%** |
| Closed lots (all) | 1,311 |
| Closed lots — options / equity | 1,242 / 69 |
| Overall win rate | 27.2% |
| Payoff (\|avg_win/avg_loss\|) | 1.42× |
| Expectancy per lot | −$2.86 |
| Wash-sale lots / disallowed loss | 273 / $5,297.84 |

**Where the loss lives — the three concentrations that explain most of it:**

1. **SPY options**: 226 lots, 21.2% win rate, **−$1,828 (49% of grand loss)**.
2. **1DTE options**: 182 lots, 23.6% win rate, **−$1,058** (worst DTE bucket).
3. **Same-day option closes**: 910 lots (73% of options!), 28.5% win rate, **−$2,466**.
   The 31+-day-hold bucket had 5 lots, 100% win rate, **+$178**.

**Where an edge actually exists** (positive-expectancy names with n≥5 lots):

| Ticker | n | Net P&L | Win rate |
|---|---|---|---|
| PYPL | 10 | +$783 | 50.0% |
| AAPL | 102 | +$292 | 36.3% |
| BUG | 9 | +$267 | 55.6% |
| RPD | 14 | +$186 | 57.1% |
| RKLB | 56 | +$166 | 35.7% |
| S | 12 | +$206 | 58.3% |
| IREN | 9 | +$81 | 77.8% |

The names where your own history says you know how to trade them are all
individual businesses, not indices, and mostly held longer than a session.

---

## Hard rules — non-negotiable for the next 90 days

### Position sizing (small-account discipline)

1. **Max single-trade loss: $50** (~5% of current $953 equity). Your data
   shows individual −$100 to −$170 SPY option wipeouts; those alone are
   10%-of-account moves at current capital.
2. **Max daily loss: $150** (three max-hits). Stop trading for the day
   the moment you print it. No revenge entries, no "one more".
3. **Max 3 open option positions at once.** Concentration failure is one
   of the reasons 1,242 lots turned into a −$3,300 result — too many
   simultaneous small bets nickel-and-diming the account.
4. **Contract count**: 1 contract per trade until account is back over
   $2,000. Every contract is a full $50 line-of-loss budget.

### Instruments — the "delete" list

Backed directly by DTE buckets and per-ticker performance:

5. **NO 0DTE options** — 340 lots, 30% win rate, **−$730**. Delete.
6. **NO 1DTE options** — 182 lots, 23.6% win rate, **−$1,058**. Delete.
7. **NO SPY options** — 226 lots, 21.2% win rate, **−$1,828**. Delete
   the entire ticker from the option universe until you've earned it
   back on individual names.
8. **NO IWM options** — 2 lots, 0% win rate, −$151. Delete.
9. **NO high-beta losers**: ASTS, ACHR, OKLO, NOW, HPQ, QBTS, QUBT,
   KULR, TE — all lost money at ≤ 22% win rate. Rebuild trust on the
   names in the whitelist first.

### Instruments — the whitelist

10. **Options ONLY on**: AAPL, PYPL, S, RPD, BUG, RKLB, IREN, QQQ.
    These are the names your own three-month history says you can trade.
    Ticker outside the list → PABS may flag it, but no live trade until
    it has produced a positive-expectancy record.
11. **NVDA on watch** — 108 lots, 29.6% win rate, −$327. Neutral. Trade
    only when PABS shows a clean multi-signal confluence; skip otherwise.

### DTE and hold discipline

12. **Minimum 7 DTE at open, target 14–30 DTE.**
    Best options bucket in your data was 15–30 DTE (+$65 net across 83
    lots at 31% win rate) and 31+ DTE (+$178 across 5 lots at 100%).
13. **Do NOT close options same-day** unless the stop is hit OR premium
    is up ≥ 50%. Same-day closes: −$2.71 avg on 910 lots. Overnight+
    holds: +$0.11 avg. The single biggest self-inflicted wound.
14. **Fixed exit plan at entry**, written into the trade note:
    - Stop: premium down 35%.
    - Target 1 (½ off): premium up 50%.
    - Target 2 (final): premium up 100% OR technical target hit.
    - Time-stop: 5 trading days with no progress → close.

    Don't renegotiate mid-trade. Renegotiation is what turned −20%
    trades into −100% wipeouts.

### Wash sales — tax + behavior tell

15. **273 lots flagged as wash sales, $5,298 disallowed loss.** The IRS
    number is the effect; the cause is re-entering losing tickers within
    30 days. **Do not re-enter a losing ticker within 30 days**, even if
    PABS re-flags it. Cool-off first.

---

## Setup context checklist — must clear before opening

For every proposed option trade, run PABS `research/context.py:compute_context_at(...)`
against the underlying at the entry bar, and verify:

- [ ] **SPY regime aligned** — no long-side option in `DOWNTREND+RISK_OFF` or
      `STRONG_DOWNTREND+*`; no short-side option in `STRONG_UPTREND+RISK_ON`.
      Field: `market.spy_regime_semantic`.
- [ ] **SPY regime confidence not `low`.** Field: `market.spy_regime_confidence`.
- [ ] **Relative strength on your side** — `relative_strength.rs_class ==
      OUTPERFORMING` for longs, `UNDERPERFORMING` for shorts. Preregistered
      thresholds ±5% / ±2% (PREREGISTRATION.md §2).
- [ ] **Not extended** — for longs: `trend.stock_distance_to_sma50_atr ≤ 3`.
      Chasing a name that is 3+ ATR above its 50-day is the pattern behind
      most of the biggest single-trade losses in your data.
- [ ] **Near a real level or in compression** — either
      `supply_demand.nearest_demand_distance_atr ≤ 1.0` (long) OR
      `compression_volatility.bb_state == COMPRESSION` OR
      `compression_volatility.squeeze_on == true`.
- [ ] **Room to work** — for longs: `supply_demand.room_to_supply_R ≥ 2.0`
      (target has room, not blocked by nearby resistance).
- [ ] **Fresh momentum, not exhausted** — `momentum.macd_state in
      {BULLISH_EXPANDING, NEUTRAL}` for longs;
      `{BEARISH_EXPANDING, NEUTRAL}` for shorts. Skip `*_FADING`.
- [ ] **Available spec cell has a real edge** — the setup's cell in the
      latest `research/results/<detector>_*/stats.md` shows
      `expectancy_R_ci_low > 0` OR `win_rate_ci_low > 45`. Point estimates
      are not enough; the bootstrap CI must clear zero.

**Two or more red boxes → PASS.** The rule is simple: it takes ≥ 6 out
of 8 to open. Not a majority-vote, a super-majority-vote — because your
own history says marginal setups compound into a −$3,300 quarter.

Every red box must be recorded on the trade card so PABS learns which
gate matters most.

---

## Post-trade feedback loop (research module)

`research/schwab_feedback.py` (ships with this playbook) reads a Schwab
realized gain/loss CSV and produces:

1. Aggregate stats — win rate, payoff, expectancy, per-ticker P&L, DTE
   buckets, hold-period buckets, wash-sale counts, biggest wins/losses.
2. **Setup-tag join** (planned, follow-up work): for each closed lot,
   compute `research/context.py:compute_context_at(underlying, spy, t_open)`
   and record which context bundle was true at entry. Once ≥ 30 lots share
   a bundle, PABS can report which bundles actually pay for you.

Run it weekly:

    python -m research.schwab_feedback <schwab_export.csv>

The output feeds the next revision of this playbook's whitelist,
blacklist, and setup checklist. Rule changes require a git commit
message that cites the numbers (no silent retuning).

---

## Behavioral rules — the process, not the trade

- **Written thesis before every entry.** Ticker, direction, expiry, strike,
  entry premium, stop, target, time-stop, checklist boxes ticked, PABS
  confidence. No thesis, no trade.
- **First 15 minutes: read-only.** Too much noise, wide spreads on options.
- **After −1 max-loss for the day**: no more trades that session, no matter
  what PABS shows.
- **After 3 consecutive losing days**: paper-trade only for the next 2
  sessions. Force the pause.
- **Weekly review (Sunday, 30 min)**: run the Schwab importer, compare
  against the last 4 weeks, update whitelist / blacklist / setup gates.
  Commit the changes here.

---

## What this playbook is NOT

- Not a promise. It is a set of self-imposed constraints backed by your
  actual results.
- Not a substitute for PABS. PABS finds setups. This playbook says which
  setups you're allowed to take AT ALL, and how big.
- Not permanent. Numbers change; the playbook changes with the next
  Schwab export + weekly review. See the git log of this file for the
  audit trail.

---

## Version log

- **v1 — 2026-09-16** — initial playbook, derived from Schwab realized
  gain/loss 06/16/2026 → 09/16/2026 (1,311 lots, −$4,249 investment
  change on $5,201 total capital in). Author: Claude Opus 4.7 session,
  from evidence in `research/schwab_feedback.py` output.
