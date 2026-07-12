# THE PROVING GROUND — Alpaca Integration + Graduation to Live

## THE PREMISE
The algorithm doesn't get real money because we hope it works. It EARNS real money by
proving it works, on a venue that can't be fooled. Alpaca paper is that venue.

Current honest state (measured, not guessed):
- n = 24 closed trades
- avg R by grade bucket: D/F = -0.013R · C-and-above = -0.205R  -> BOTH NEGATIVE
- grader is anti-predictive (num_edges rho = -0.398 vs realized R)
- live emission bugs: 0.4:1 R:R accepted; bearish stance emitted a LONG
- small-cap scanner: just unblocked, ~0 validated triggers
- sector engine (the actual edge): not built

That is not a system to fund. It is a system to VALIDATE.

---
## STAGE 1 — ALPACA PAPER AS THE EXECUTION VENUE (build now)
Replace the internal paper simulation with real Alpaca paper orders. The internal sim fills
at your assumed price; Alpaca fills at the market's price, rejects bad orders, gaps through
stops, slips fills.
- Alpaca PAPER endpoint only (`https://paper-api.alpaca.markets`). Keys in `.env`.
- Every emitted idea -> a real bracket order: entry limit + stop + take-profit.
- Record the FILL not the intent: fill_price, fill_time, slippage_bps, rejected,
  partial_fill, gap_through_stop.
- Track slippage_bps per lane + price tier. Sub-$5 names will show ugly numbers.
- Free-roll ladder = real bracket + OCO trims.
- Intraday bars from Alpaca for 4h/1h + day trades (verify tier/limits first).

## STAGE 2 — RISK CONTROLS (before any real money; build now)
- Position sizing: `shares = (equity * risk_pct) / |entry - stop|`, default 0.5%. Never fixed.
- Max open risk: sum open risk <= 5% equity. Blocks new entries above.
- Max daily loss: -2% -> HALT new entries for the day.
- Max drawdown kill-switch: -10% from peak -> HALT ALL AUTO-ENTRY, manual restart.
- Per-lane exposure cap: no lane > 30% of open risk.
- Correlation cap: max 3 open positions per sector (the sympathy-engine guard).
- Liquidity guard: size <= 1% of 20d avg daily volume.
- PDT awareness: < $25k restricts day trades. Track + enforce.
- Event guard: no auto-entry within 2d of earnings unless the lane allows.
Each gets a test + a visible utilization panel.

## STAGE 3 — GRADUATION CRITERIA (measured on Alpaca PAPER fills)
| Gate | Threshold |
|---|---|
| Closed trades | n >= 100 |
| Expectancy | >= +0.20R |
| Profit factor | >= 1.3 |
| Max drawdown | <= 15R |
| Regimes covered | >= 2 |
| Slippage-adjusted | expectancy still >= +0.20R after real fills |
| Zero emission bugs | 0 below R:R floor, 0 incoherent-direction |
| Per-lane | each funded lane >= +0.10R over n >= 20 |
**Lanes graduate INDIVIDUALLY.**

## STAGE 4 — GOING LIVE (ramp, never flip to $100k)
1. Manual-approval live (20 trades min). 2. Auto 10% (30 trades, compare live vs paper).
3. Scale 25% -> 50% on performance. Never 100%. 4. Any drawdown-kill breach -> auto-revert
to paper. Paper book runs in parallel on the SAME signals for a live-vs-paper divergence
measurement.

## STAGE 5 — SHADOW TRACKING (accelerates LEARNING, not graduation)
Score every candidate daily + log family breakdown; track 20-day forward outcome for top
~50/lane whether or not it triggered (~1,000 obs/month). Shadows tune the model; only real
Alpaca paper fills count toward graduation. Never confuse the two.

## HONEST TIMELINE
Bugs fixed + engines unified + Alpaca wired: ~2-4 weeks. n=100 on paper: ~4-8 months.
Manual-approval live: +1-2 months. Meaningful auto-execute: 6-12 months.
The upside: at the end you have a MEASUREMENT of which edges work, in which regime, at what
size. Almost nobody has that.
