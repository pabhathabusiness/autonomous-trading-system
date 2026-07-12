# Addendum 6 — Small-Cap Hold Bands (timeframe variety)
Every small-cap lane gains a HOLD BAND, chosen by the SETUP not the trader. Determines stop
width, target, time-stop, and which stats bucket. Store `hold_band` on every trigger + paper trade.
### The four bands
| Band | Hold | Stop | Target | Time-stop | Driven by |
|---|---|---|---|---|---|
| overnight | 1-2d | 0.6x ATR | 1.5x ATR | 2d | gap/momentum continuation |
| short     | 3-5d | 1.0x ATR | 2.0x ATR | 5d | daily breakout / bounce |
| medium    | 1-3wk| 1.5x ATR | 3.0x ATR | 15d | WEEKLY breakout momentum |
| position  | 3-8wk| 2.0x ATR | 4.0x ATR | 40d | Special/Value lanes only |
R:R floor per band: overnight 1.8 · short 2.0 · medium 2.2 · position 2.2.
A trigger that can't meet its band R:R floor does NOT open — re-checks a longer band, opens there
if it qualifies. Bands compete; the setup lands where it fits.
### NEW medium band — WEEKLY breakout momentum
Resample daily -> weekly (df.resample('W-FRI')). Weekly signals as sub-family inside `structure`:
- weekly_breakout: this week close > highest close of prior 8 weekly bars, weekly vol > 1.5x 8wk avg
- weekly_base: >=6 weekly bars total range <30% (weekly coil)
- weekly_higher_lows: 3+ consecutive weekly higher lows
- consecutive_up_weeks feeds here; weekly_rel_volume
medium-band trigger REQUIRES >=1 of weekly_breakout/weekly_base + weekly_higher_lows.
Chip: `WEEKLY BREAKOUT` (highest-conviction structure on free daily data).
### overnight band — DATA LIMIT HONESTY
No intraday. Model: entry = next day OPEN; exit at stop/target via next day HIGH/LOW else close day2.
Log gap_pct=(next open - prior close)/prior close on every overnight trade. HONESTY FLAG on page:
"Overnight fills modeled at next open — no intraday data. Real slippage worse." Positive expectancy
+ large median gap_pct => probably data artifact, flag it.
### Band eligibility by lane
| Lane | overnight | short | medium | position |
|---|---|---|---|---|
| Runner   | YES | YES | no | no |
| HailMary | YES | YES | no | no |
| Bounce   | no  | YES | YES | no |
| Coiled   | no  | YES | YES | no |
| Value    | no  | no  | YES | YES |
| Special  | no  | no  | YES | YES |
### Stats: band is first-class
/smallcaps/record gets a SECOND comparison table by hold band (n, expectancy, win rate, avg hold,
avg MAE, best/worst R) alongside by-lane. Answers: is my edge in a SETUP or a TIMEFRAME?
Filter chips gain hold_band. learnings.json keys rules by (lane, band). Report both tables.
### Time-stop enforcement
Every band time-stop HARD, auto-closes paper trade at max hold. Log hit_time_stop=true. High
time-stop rate in a band = band wrong for that setup = a finding.
