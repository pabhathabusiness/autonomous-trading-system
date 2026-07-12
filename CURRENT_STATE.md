# CURRENT_STATE.md

Read-only audit of the Autonomous Trading System as deployed to the live droplet
(`pabs-trading.duckdns.org`, DigitalOcean, `/home/trading/autonomous-trading-system`).
Real data below is pulled from the live SQLite DB (78 trades). No code was changed
to produce this document.

> Note: item 7 references "the attached spec." No spec file was attached to the
> request, so the GAPS section is derived from (a) the specific fields the request
> named (`exit_reason`, `r_realized`, `atr`, `days_to_earnings`, …) and (b) the
> requirements established across this build. Flagged where inferred.

---

## 1. STACK

| Layer | What |
|---|---|
| **Language** | Python 3 (server venv, yfinance 1.5.1, pandas) |
| **Web framework** | FastAPI + Uvicorn (`src/api_server.py`), served on `127.0.0.1:8000` behind nginx + Let's Encrypt; HTTP basic auth |
| **DB / storage** | **SQLite**, single file `data/trading_system.db` (via `src/database.py`; one `Database` class, connection-per-op, additive `_migrate()`). No Postgres. |
| **Scanner runtime** | **Background daemon thread**, not cron. `src/scheduler.py` (`AutonomousScheduler`) starts on FastAPI startup: a **monitor** tick every 60s (always) that closes open trades at stop/target, and a **scan** every 15 min **gated to US market hours** that opens new trades. Replaces the old manual "Run Scan" button. |
| **Order execution** | **None live.** `autonomous.auto_execute = false`. Paper only. `src/execution_guard.py` hard-walls any order to the Alpaca **paper** host + `algo` book (fails closed). Alpaca is read-only for prices today. |
| **Dashboard data** | **JSON API routes** (`/api/*`), polled by `src/static/app.js`. No static JSON files. Key routes: `/api/live` (5s), `/api/scheduler` (15s), `/api/market-overview` + `/api/bias-strip` + `/api/log/algo` (dashboard), `/api/drilldown/{symbol}` (on click), `/api/sectors`, `/api/proposals`, `/api/regime`. StaticFiles serves the SPA from `src/static/` with no-cache headers. |
| **Data sources** | Alpaca IEX = live last-trade prices; yfinance = daily/weekly/intraday bars, fundamentals, VIX, news, earnings. Never blended (side-by-side, bar-age stamped). |

---

## 2. TRADE SCHEMA

The trade record is the **`paper_trades`** table. Effective columns as deployed
(`PRAGMA table_info(paper_trades)` on the live DB — base `CREATE TABLE` in
`database.py` SCHEMA plus additive migration columns):

```
id                INTEGER  (PK)
proposal_id       INTEGER  (UNIQUE)
symbol            TEXT
account_type      TEXT
strategy          TEXT      -- engine: swing | short_term | coiling | downside
direction         TEXT      -- long | short
confidence        TEXT      -- HIGH | MEDIUM | LOW
num_edges         INTEGER
edges_fired       TEXT      -- comma-joined confluence flag names
sector_name       TEXT
entry_price       REAL
stop_loss         REAL
target_price      REAL
expected_timeframe TEXT
entry_date        TEXT      -- ISO8601 UTC
max_hold_days     INTEGER
status            TEXT      -- open | closed
exit_price        REAL
exit_date         TEXT
return_pct        REAL
outcome           TEXT      -- win | loss   (no separate target/stop/timeout reason)
-- ---- migration-added (book/journal/grade) ----
book              TEXT      -- 'algo' for scanner trades (Log B); NULL on legacy
source            TEXT
archetype         TEXT      -- trending_pullback_to_pivot | reversal | breakout_continuation
timeframe_band    TEXT      -- "1-2 day" | "1-2 week swing"
entry_type        TEXT      -- pullback-zone | reversal-break | breakout/retest
pattern           TEXT
rs_vs_spy         REAL
compression_tf    TEXT
planned_rr        REAL
process_grade     TEXT      -- A|B|C|D|F | UNGRADED
process_score     REAL      -- 0-100
process_flags     TEXT      -- JSON array
process_notes     TEXT
shares            REAL
position_value    REAL
r_multiple        REAL      -- realized return / planned risk-to-stop
pnl_usd           REAL      -- shares * per-share move
```

### ONE REAL CLOSED ROW (exactly as stored, live DB)
```json
{
 "id": 78, "proposal_id": 269, "symbol": "SRPT", "account_type": "personal",
 "strategy": "short_term", "direction": "long", "confidence": "LOW",
 "num_edges": 3, "edges_fired": "downtrend_break, weekly_pivot, rsi_room",
 "sector_name": "Biotechnology",
 "entry_price": 18.950000762939453, "stop_loss": 18.0025, "target_price": 20.2765,
 "expected_timeframe": "1-2 days", "entry_date": "2026-07-11T00:15:38.449228+00:00",
 "max_hold_days": 4, "status": "closed",
 "exit_price": 20.2765, "exit_date": "2026-07-11T05:17:51.219825+00:00",
 "return_pct": 7.0, "outcome": "win",
 "book": null, "source": null, "archetype": null, "timeframe_band": null,
 "entry_type": null, "pattern": null, "rs_vs_spy": null, "compression_tf": null,
 "planned_rr": null, "process_grade": null, "process_score": null,
 "process_flags": null, "process_notes": null, "shares": null,
 "position_value": null, "r_multiple": 1.4, "pnl_usd": null
}
```

### ONE REAL OPEN ROW (exactly as stored, live DB)
```json
{
 "id": 77, "proposal_id": 265, "symbol": "INO", "account_type": "agentic",
 "strategy": "short_term", "direction": "long", "confidence": "MEDIUM",
 "num_edges": 4, "edges_fired": "bb_squeeze, macd_4h, volume_surge, rsi_room",
 "sector_name": "Biotechnology",
 "entry_price": 1.1799999475479126, "stop_loss": 1.121, "target_price": 1.27,
 "expected_timeframe": "1-2 days", "entry_date": "2026-07-11T00:15:38.406211+00:00",
 "max_hold_days": 4, "status": "open",
 "exit_price": null, "exit_date": null, "return_pct": null, "outcome": null,
 "book": null, "source": null, "archetype": null, "timeframe_band": null,
 "entry_type": null, "pattern": null, "rs_vs_spy": null, "compression_tf": null,
 "planned_rr": null, "process_grade": null, "process_score": null,
 "process_flags": null, "process_notes": null, "shares": null,
 "position_value": null, "r_multiple": null, "pnl_usd": null
}
```

> Note the `edges_fired` on these show `rsi_room` — that's the **pre-refactor** flag
> name; the deployed code now emits `mfi_room` (MFI replaced RSI). These 78 rows
> were written before that code shipped (see §3).

---

## 3. FIELD AUDIT (across the 78 legacy trades: 54 open, 24 closed)

**Always populated (78/78):** `id, proposal_id, symbol, account_type, strategy,
direction, confidence, num_edges, edges_fired, sector_name, entry_price,
stop_loss, target_price, expected_timeframe, entry_date, max_hold_days, status`

**Sometimes null (populated only on closed):**
`exit_price` 24/78 · `exit_date` 24/78 · `return_pct` 24/78 · `outcome` 24/78 ·
`r_multiple` **10/78**

**Always null (0/78)** — the migration-added columns; every one of the 78 predates
the code that writes them:
`book, source, archetype, timeframe_band, entry_type, pattern, rs_vs_spy,
compression_tf, planned_rr, process_grade, process_score, process_flags,
process_notes, shares, position_value, pnl_usd`

### Specifically requested fields
| Field | Status | Detail |
|---|---|---|
| `direction` | **always populated** (78/78) | `long`/`short`; the 78 are predominantly `long` |
| `exit_price` | **sometimes null** (24/78) | set on close only; null on the 54 open |
| `exit_reason` | **COLUMN DOES NOT EXIST** | closest is `outcome` (win/loss) + `exit_price`/`exit_date`; no target/stop/timeout enum stored |
| `r_realized` | **COLUMN DOES NOT EXIST** | analog is **`r_multiple`**, populated 10/78 (only trades closed by the *new* `close_paper_trade`; 14 older closes have none) |
| `timeframe_band` | **always null** (0/78) | column exists; legacy predates it (new trades will populate) |
| `atr` | **COLUMN DOES NOT EXIST** | ATR not computed or stored anywhere |
| `sector` | **always populated** (78/78) | column is named **`sector_name`** |
| `days_to_earnings` | **COLUMN DOES NOT EXIST** | earnings dates now available via `/api/market-overview` but never joined onto trades |

---

## 4. SCORING

Two scores. `quality_score` (0–10, the buy engines) is the sum of five capped
dimensions; `coil_score` (0–10, coiling) is a weighted edge ratio. Aggregation
(`src/technical_analyzer.py`):

```python
_DIM_CAP = 2.0
_DIMENSIONS = ("structure", "momentum", "volatility", "volume", "rel_strength")

def _aggregate_dims(dims, caps=None):
    caps = caps or {}
    dim_scores = {d: round(min(caps.get(d, _DIM_CAP), sum(s["points"] for s in subs)), 2)
                  for d, subs in dims.items()}
    quality = round(sum(dim_scores.values()), 2)          # direct 0-10 sum, each dim capped 2.0
    fired = [s["name"] for subs in dims.values() for s in subs if s["fired"]]
    return dim_scores, quality, fired, len(fired)
```

Coiling score (`analyze_coiling`), unchanged compression-thesis ranking:
```python
earned   = sum(e["points"] for e in edges)
possible = sum(e["max_points"] for e in edges)
coil_score = round(10 * earned / possible, 2) if possible else 0.0
```

Separate **process grade** (A–F, outcome-independent) is computed in
`src/process_grader.py` (`grade()`), weighting entry_discipline 26 /
timeframe_confluence 18 / confluence_breadth 16 / stop_at_structure 14 /
rr_quality 12 / sector_alignment 8 / rel_strength 6.

### Every confluence flag the scanner can emit (by engine → dimension)

**swing `analyze`:** `mtf_structure`, `chart_pattern`, `demand_zone_entry`
(structure) · `ema_9_21`, `ema_20_50`, `ema_50_200`, `macd_daily`,
`macd_mtf_confluence`, `momentum_roc`, `mfi_regime` (momentum) · `squeeze`,
`bb_position`, `compression_resolve_up` (volatility) · `volume_confirmation`,
`relative_volume`, `buying_pressure`, `volume_profile` (volume) · `rs_vs_spy_20`,
`rs_vs_spy_60` (rel_strength)

**`analyze_short_term`:** `bb_squeeze`, `compression_resolve_up` (volatility) ·
`macd_4h`, `ema_9_21`, `ema_20_50`, `mfi_room` (momentum) · `downtrend_break`,
`weekly_pivot`, `inside_day_macd` (structure) · `volume_surge` (volume) ·
`rs_vs_spy_20`, `rs_vs_spy_60` (rel_strength)

**`analyze_coiling`:** `monthly_squeeze`, `quarterly_squeeze`, `weekly_squeeze`,
`daily_squeeze`, `flat_price`, `accumulation`, `volume_building`, `mfi_room`,
`base_intact`

**`analyze_downside`:** `mtf_downtrend` (structure) · `ema_9_21_down`,
`ema_20_50_down`, `ema_50_200_down` (death cross), `macd_daily_bear`,
`macd_mtf_bear`, `momentum_down`, `mfi_weak` (momentum) · `bollinger_breakdown`,
`bollinger_rejection`, `compression_resolve_down` (volatility) ·
`volume_confirmation`, `relative_volume`, `distribution` (volume) · `rs_vs_spy_20`,
`rs_vs_spy_60` (rel_strength)

> R:R and analyst target are deliberately NOT scored (R:R is a gate + grade input).

---

## 5. UNIVERSE

Defined in **`config/universe.json`** (path from `config.universe.sector_tickers_file`),
loaded by `src/sector_analyzer.py`. ~46 sectors, each `{name, etf, candidates[]}`.
The screener filters these candidates live by price/volume/fundamentals; only "hot"
sectors are scanned per run. Full file:

```json
{
  "sectors": [
    {"name": "Technology", "etf": "XLK", "candidates": ["AAPL","MSFT","DELL","HPQ","IBM","ORCL","CSCO","QCOM","AVGO","SMCI","TXN","ANET"]},
    {"name": "Software", "etf": "IGV", "candidates": ["CRM","ORCL","ADBE","PLTR","SOUN","NOW","SNOW","TEAM","DDOG","PATH","MDB","HUBS","GTLB"]},
    {"name": "Semiconductors", "etf": "SMH", "candidates": ["NVDA","AMD","INTC","MU","ON","AVGO","QCOM","TXN","MRVL","SWKS","MCHP","TSM"]},
    {"name": "Semiconductor Equipment", "etf": "PSI", "candidates": ["AMAT","LRCX","KLAC","ASML","TER","ENTG","ONTO","ACLS","COHU"]},
    {"name": "Cybersecurity", "etf": "CIBR", "candidates": ["CRWD","PANW","FTNT","ZS","NET","S","OKTA","CYBR","TENB","QLYS","RPD"]},
    {"name": "Cloud Computing", "etf": "SKYY", "candidates": ["CRM","NOW","WDAY","SNOW","DOCN","NET","DDOG","MDB","ORCL","FSLY","BOX"]},
    {"name": "Internet", "etf": "FDN", "candidates": ["META","GOOGL","AMZN","NFLX","ETSY","PINS","SNAP","ABNB","UBER","DASH","EBAY","RDDT"]},
    {"name": "Robotics & AI", "etf": "BOTZ", "candidates": ["ISRG","ROK","ABB","NVDA","PATH","TER","ZBRA","AVAV","SYM"]},
    {"name": "Fintech", "etf": "FINX", "candidates": ["PYPL","XYZ","SOFI","UPST","AFRM","COIN","HOOD","NU","TOST","BILL","GPN"]},
    {"name": "Financials", "etf": "XLF", "candidates": ["BAC","WFC","C","JPM","SCHW","GS","MS","USB","PNC","AXP","BLK","COF"]},
    {"name": "Regional Banks", "etf": "KRE", "candidates": ["KEY","CFG","ZION","TFC","FITB","HBAN","RF","MTB","CMA","ALLY","PNC"]},
    {"name": "Insurance", "etf": "KIE", "candidates": ["AIG","MET","PRU","ALL","TRV","PGR","HIG","CB","AFL","LNC","CINF"]},
    {"name": "Energy", "etf": "XLE", "candidates": ["XOM","CVX","COP","OXY","EOG","SLB","PSX","VLO","MPC","HES","DVN","WMB"]},
    {"name": "Oil & Gas E&P", "etf": "XOP", "candidates": ["DVN","APA","EOG","FANG","CTRA","MTDR","AR","RRC","SM","OVV","PR"]},
    {"name": "Oil Services", "etf": "OIH", "candidates": ["SLB","HAL","BKR","NOV","FTI","WFRD","CHX","LBRT","TDW"]},
    {"name": "Solar", "etf": "TAN", "candidates": ["FSLR","ENPH","SEDG","RUN","JKS","NXT","ARRY","SHLS","CSIQ","MAXN"]},
    {"name": "Clean Energy", "etf": "ICLN", "candidates": ["PLUG","FCEL","BE","BLDP","ENPH","FSLR","RUN","NEE","BEP","AMRC"]},
    {"name": "Uranium & Nuclear", "etf": "URA", "candidates": ["CCJ","UEC","DNN","UUUU","NXE","LEU","SMR","OKLO","URG"]},
    {"name": "Healthcare", "etf": "XLV", "candidates": ["PFE","JNJ","MRK","ABBV","UNH","TMO","ABT","DHR","BMY","AMGN","CVS","MDT"]},
    {"name": "Biotechnology", "etf": "XBI", "candidates": ["MRNA","NVAX","OCGN","INO","VRTX","REGN","GILD","BIIB","ALNY","SRPT","CRSP","BNTX","EXEL"]},
    {"name": "Pharmaceuticals", "etf": "PPH", "candidates": ["BMY","GILD","LLY","VTRS","PFE","MRK","ABBV","ZTS","JNJ","AZN","TEVA"]},
    {"name": "Medical Devices", "etf": "IHI", "candidates": ["MDT","SYK","BSX","ABT","ISRG","EW","ZBH","BDX","DXCM","GEHC","PODD"]},
    {"name": "Consumer Discretionary", "etf": "XLY", "candidates": ["TSLA","HD","NKE","SBUX","MCD","LOW","TJX","BKNG","CMG","ROST","F","GM"]},
    {"name": "Retail", "etf": "XRT", "candidates": ["GME","KSS","M","JWN","BBWI","TGT","DG","DLTR","BBY","ULTA","AEO"]},
    {"name": "Homebuilders", "etf": "XHB", "candidates": ["DHI","LEN","PHM","KBH","TOL","NVR","MTH","TMHC","BLDR","MAS","IBP"]},
    {"name": "Consumer Staples", "etf": "XLP", "candidates": ["KO","PEP","PG","WMT","COST","MDLZ","CL","KMB","GIS","KHC","TAP"]},
    {"name": "Industrials", "etf": "XLI", "candidates": ["GE","HON","CAT","DE","MMM","LMT","UPS","BA","EMR","ETN","PH","CMI"]},
    {"name": "Aerospace & Defense", "etf": "ITA", "candidates": ["BA","LMT","RTX","NOC","GD","LHX","HII","TDG","AXON","HWM","KTOS"]},
    {"name": "Transportation", "etf": "IYT", "candidates": ["UPS","FDX","CSX","UNP","NSC","ODFL","JBHT","CHRW","DAL","LUV","XPO"]},
    {"name": "Materials", "etf": "XLB", "candidates": ["LIN","SHW","ECL","NEM","FCX","APD","DOW","DD","NUE","CTVA","ALB"]},
    {"name": "Metals & Mining", "etf": "XME", "candidates": ["CLF","X","AA","FCX","NUE","STLD","RS","VALE","TECK","MP","SCCO"]},
    {"name": "Gold Miners", "etf": "GDX", "candidates": ["GOLD","AEM","KGC","NEM","FNV","WPM","AU","HMY","EGO","BTG","IAG"]},
    {"name": "Steel", "etf": "SLX", "candidates": ["MT","NUE","STLD","RS","CLF","X","CMC","TX","WOR"]},
    {"name": "Agriculture", "etf": "MOO", "candidates": ["ADM","BG","MOS","CF","NTR","DE","CTVA","FMC","AGCO"]},
    {"name": "Utilities", "etf": "XLU", "candidates": ["DUK","SO","NEE","AEP","D","EXC","SRE","XEL","ED","PEG","VST"]},
    {"name": "Real Estate", "etf": "IYR", "candidates": ["O","SPG","PLD","AMT","CCI","EQIX","PSA","DLR","VICI","WELL","AVB"]},
    {"name": "Communication Services", "etf": "XLC", "candidates": ["T","VZ","TMUS","CMCSA","DIS","NFLX","GOOGL","META","CHTR","EA","WBD"]},
    {"name": "Media & Entertainment", "etf": "PBS", "candidates": ["DIS","WBD","PARA","FOXA","NFLX","CMCSA","LYV","ROKU","NWSA"]},
    {"name": "Cannabis", "etf": "MJ", "candidates": ["TLRY","CGC","ACB","SNDL","CRON","OGI","GRWG"]},
    {"name": "Airlines", "etf": "JETS", "candidates": ["AAL","UAL","DAL","LUV","JBLU","ALK","HA","ALGT","SKYW"]},
    {"name": "Quantum Computing", "etf": "QTUM", "candidates": ["IONQ","RGTI","QBTS","QUBT","LAES","ARQQ"]},
    {"name": "Space & Satellites", "etf": "UFO", "candidates": ["RKLB","LUNR","ASTS","PL","RDW","SPCE"]},
    {"name": "AI & Data Infrastructure", "etf": "IGV", "candidates": ["NVDA","AVGO","SMCI","VRT","PLTR","ANET","DELL","NBIS","CRDO"]},
    {"name": "Obesity & GLP-1", "etf": "XLV", "candidates": ["LLY","NVO","VKTX","AMGN","HIMS","STOK"]},
    {"name": "Mixed & Other Stocks", "etf": "SPY", "candidates": ["RIVN","LCID","NIO","COIN","HOOD","DKNG","RBLX","U","SNAP","SHOP","ROKU","CVNA","RIOT","MARA","MSTR","GME","AMC","CHPT","LYFT","DJT"]}
  ]
}
```

Additional fixed symbol sets in `config.json` (not in universe.json):
- `dashboard.bias_strip` — SPY + MAG-7 (AAPL, MSFT, NVDA, GOOGL, AMZN, META, TSLA).
- `sector_leaders` — MAG-7 + AVGO, NFLX (grade sector-leader carve-out).
- Market-overview indices — SPY, QQQ, IWM (hard-coded in `market_overview.build`).

---

## 6. EXISTING FEATURES (do not rebuild/break)

**Top nav (4 views):** Dashboard · Track Record · Sectors · More.

**Dashboard:**
- **Market Context** — index tiles (SPY/QQQ/IWM), VIX (level + calm/normal/elevated/high-fear), breadth proxy (% of sector ETFs green), "What's coming" (static economic calendar + held-name earnings, merged by date), market news headlines.
- **Market Bias strip** — SPY + MAG-7 cards: live price, session %, bias tag (Bullish/Bearish/Neutral), conditional key levels ("above X / watch Y"). Click → detail sheet.
- **Sector Strength board** — Strongest (top 5) / Weakest (bottom 3) / Watching-leaning (turning sectors) with lean arrows + sparklines.
- **Trade Ideas feed** — open algo trades: ticker, archetype chip (Pullback/Reversal/Breakout), timeframe-band chip, engine chip, quality chip, full plan (entry→stop/target), R:R, and the **grade badge as the row headline**.

**Detail sheet (slide-in):**
- For a bias card: stance/levels + **MAG-7 drill-down** — 15m/30m/1h/4h/daily bias with squeeze/MACD tags; trade plan shown **only** on real confluence (compression + MACD-cross + pivot), never manufactured.
- For a trade: plan, archetype, band, R:R, quality, RS-vs-SPY, grade+score, process notes + flag chips, confluences, rationale, live block (dist to stop/target).

**Track Record (Log B):** summary scorecards (graded trades, win rate, avg R, realized P&L, grade distribution — legacy excluded); per-trade table with **All/Open/Closed filter**; columns Date · Symbol · Setup · Band · Entry→Stop/Target · R:R · Grade · Feedback · Outcome (Win/Loss) · R · Return · P&L.

**Sectors:** heat map (click ETF → live per-sector setup scan).

**More:** market regime card, accounts, performance, **Trade Proposals** (tabs: Top / Short-term / Coiling / Downside / Sector S+M / By Sector / By Timeframe — full detail: R:R, quality, edges, reasoning, approve/reject), **sortable live book** (position value / $P&L / %P&L / RS / dist-to-stop / dist-to-target / days; click-header sort held **stable across the 5s refresh**), approved positions.

**Grade chip system:** `A`/`B`/`C` = filled deep-violet ramp, `D`/`F` = outline, `UG` = amber dashed (UNGRADED), `L` = grey (legacy pre-grading). Grade is the process headline; P&L is muted/secondary.

**Live updates:** engine-status pill (`/api/scheduler` 15s); live book + trade ideas (5–6s, bar-age stamped); market context 60s; no manual reload; no "Run Scan" button; Catalyst Watchlist removed (DB table retained).

**Guardrails:** `auto_execute=false`; `execution_guard` paper-vs-real wall; real-money accounts never auto-executed.

---

## 7. GAPS (relative to the named fields + build requirements)

Legend: **(a)** new code · **(b)** backfill migration · **(c)** change to existing code (RISKY).

| Gap | Type | Notes |
|---|---|---|
| **`exit_reason`** (target / stop / timeout / manual) not stored | **(c) RISKY** + (a) column | The resolver (`paper_trader.resolve_open`, `scheduler.close_on_live_cross`) already *knows* the reason (it branches on hit_target/hit_stop/aged-out) but only records `outcome` win/loss. Requires touching the close path + a migration. |
| **`atr`** not computed or stored | **(a)** | New indicator in `indicators.py` + store on the record; no existing consumer. |
| **`days_to_earnings`** not on trade records | **(a)** | Earnings dates already fetched (`market_overview._earnings`); needs a new column + wiring at trade-open. New. |
| **`r_multiple`** only 10/78 closed | **(b)** | New closes compute it; backfill the 14 older closed rows (derivable from stored entry/stop/return_pct). Pure data migration, low risk. |
| **`pnl_usd`** 0/78 | **(b) partial** | Needs `shares`, which legacy rows lack → not backfillable for legacy; new trades store both. No new code needed. |
| Journal/grade columns (`book, archetype, timeframe_band, process_grade, …`) null on all 78 | **(b) partial** | New trades populate them at write-time (verified live: analyze→grade produces archetype+letter grade). Legacy `archetype`/`grade` can't be recovered (no stored analysis); R:R/quality/edges/rationale are already **surfaced at read-time** via the `get_algo_trades` proposal JOIN, so no migration is strictly required for display. |
| `edges_fired` on legacy rows use old flag name (`rsi_room`) | — | Cosmetic/historical only; new rows emit `mfi_room`. No action. |
| No `exit_reason`/`atr`/`days_to_earnings` means feedback analytics can't yet segment by exit-type, volatility regime, or earnings proximity | **(a)** | Depends on the three new fields above. |

**Lowest-risk first:** (b) `r_multiple` backfill and the (a) new fields (`atr`,
`days_to_earnings`, `exit_reason` column) are additive. The **only (c) risky item**
is wiring `exit_reason` into the live close path — that touches `resolve_open` /
`close_on_live_cross`, which are the functions that actually close real (paper)
positions, so it needs care + verification against the running monitor.

---
*Generated read-only from live DB + source. No files other than this one were created or modified.*
