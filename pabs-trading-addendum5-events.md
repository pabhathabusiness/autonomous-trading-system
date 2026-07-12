# Addendum 5 — Scheduled Catalyst Events (with empirical reactivity gating)
Core principle: an event is only an edge if the symbol has PROVEN it reacts to that event
type historically. Measure reactivity; never assume it.
---
## PART 1 — EVENT REGISTRY (new table `catalyst_events`)
`catalyst_events: symbol, event_type, event_date, is_estimated, source, confirmed, notes`
Event types: earnings (Finnhub /calendar/earnings, BMO/AMC), deliveries (curated),
product_event (curated: AAPL Sept, NVDA GTC Mar), investor_day (news/8-K), conference_presentation
(news, LOW), guidance_update (news), fda_pdufa (curated/news, highest reactivity for small caps),
lockup_expiry (/calendar/ipo +180d, NEGATIVE), index_rebalance (quarterly, swing book).
`recurring_events.json` — ~20-40 names max, hand-maintained (TSLA deliveries quarter_end+2d,
NVDA GTC annual month 3, AAPL iPhone annual month 9). SMALL and manual, not a scraper.
---
## PART 2 — REACTIVITY GATE
Per (symbol, event_type) from historical daily OHLCV (need >=4 occurrences):
  event_rel_vol = vol on event day / 20d avg before; event_abs_move = |close(T+1)-close(T-1)|/close(T-1)
  reactivity_score = 0.5*clamp((median(event_rel_vol)-1.5)/1.5,0,1) + 0.5*clamp((median(event_abs_move)/baseline_daily_move)-1,0,1)
  store occurrences_n, median_rel_vol, median_abs_move (all DISPLAYED)
GATE — event contributes to catalyst family ONLY IF:
1. occurrences_n >= 4 (else UNPROVEN EVENT, contributes 0)
2. reactivity_score >= 0.5
3. within lookahead for lane band (scalp 3d · swing 7d · position 21d)
Everything else displayed as context, scores ZERO. Data decides which events matter.
Card: `EVENT: deliveries in 4d · reactivity 0.78 (n=8, 3.2x vol, 6.1% move)`.
---
## PART 3 — CONFIRMATION (volume building INTO it)
pre_event_confirmation = rel_vol last 3d > 1.3x baseline AND price holding above 20d SMA (longs).
Event + reactivity proven + volume building = full 1.0. + no volume building = 0.5 + NOT CONFIRMED
chip. Unproven reactivity = 0.0 regardless.
---
## PART 4 — POLARITY + POST-EVENT TRAP
polarity per type: positive-lean (product_event, fda_pdufa binary, index_rebalance add);
negative-lean (lockup_expiry, offering); neutral/binary (earnings, deliveries, guidance — COIN FLIPS).
RULE: binary events -> may NOT open a directional trade purely on the event. May only score into
catalyst family for a setup ALREADY with 3 other families firing, OR flag on Coiled watchlist as
expansion trigger (direction set by the break).
days_since_event stored; trade after binary = post_event_drift tag, tracked separately. Trade held
THROUGH a binary event -> EVENT RISK red flag on open position. Special lane options + binary event
inside option life -> IV CRUSH RISK warning (not a rule).
---
## PART 5 — SCOPE DISCIPLINE
Curated recurring ~20-40 names max hand-maintained. Everything else from Finnhub earnings calendar +
news classifier (A4). Reactivity gate kills unproven automatically. catalyst family capped 1.0.
3-family rule governs. Report after backfill: how many (symbol,event_type) pairs cleared the gate.
<20 across universe is the honest answer — most stocks don't have event franchises.
---
## PART 6 — BUILD ORDER
1. catalyst_events table + earnings calendar backfill. 2. reactivity engine (pure math). 3. Report
reactivity table BEFORE wiring. 4. recurring_events.json (10 obvious names). 5. wire into catalyst
family w/ confirmation+polarity. 6. IV crush warning on Special options chips.
---
## ADDENDUM 5b — Mag 7 / index briefing cards (context-only)
Cards in news drawer: bias, RS, 52w position, "Events to Watch" (reactivity numbers), classified
news, LLM "Notes" prose (3-5 bullets, MUST state where technicals and news DISAGREE, MUST end with
no recommendation). HARD: NO entry/stop/target fields ever render. Mag7 + index symbols EXCLUDED
from all scanner lanes. Header "Context only — no trade plan."
