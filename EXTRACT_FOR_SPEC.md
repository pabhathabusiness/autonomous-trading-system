# EXTRACT_FOR_SPEC.md

Consolidated, verbatim extract for pasting into another chat. All DB values are
real, pulled live from `data/trading_system.db` on the droplet (read-only). Every
factual claim is followed by the exact SQL/grep that produced it. No code was
modified; this file is the only thing created.

Ambiguity note: the task references "the attached spec" (item 8) — none was
attached, so §8 is copied verbatim from `CURRENT_STATE.md`.

---

## 1. TRADE SCHEMA (verbatim)

`-- SQL: SELECT name, sql FROM sqlite_master WHERE type='table' AND name IN ('paper_trades','proposals')`

**`paper_trades`** (base `CREATE`; note the migration columns were added via
`ALTER TABLE`, so sqlite_master shows them appended on the `outcome` line):
```sql
CREATE TABLE paper_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id INTEGER,
    symbol TEXT NOT NULL,
    account_type TEXT,
    strategy TEXT,
    direction TEXT DEFAULT 'long',
    confidence TEXT,
    num_edges INTEGER,
    edges_fired TEXT,
    sector_name TEXT,
    entry_price REAL NOT NULL,
    stop_loss REAL NOT NULL,
    target_price REAL NOT NULL,
    expected_timeframe TEXT,
    entry_date TEXT NOT NULL,
    max_hold_days INTEGER,
    status TEXT DEFAULT 'open',
    exit_price REAL,
    exit_date TEXT,
    return_pct REAL,
    outcome TEXT, book TEXT, source TEXT, archetype TEXT, timeframe_band TEXT, entry_type TEXT, pattern TEXT, rs_vs_spy REAL, compression_tf TEXT, planned_rr REAL, process_grade TEXT, process_score REAL, process_flags TEXT, process_notes TEXT, shares REAL, position_value REAL, r_multiple REAL, pnl_usd REAL,
    UNIQUE(proposal_id)
)
```

**`proposals`**:
```sql
CREATE TABLE proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    account_type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    sector_name TEXT,
    entry_price REAL,
    stop_loss REAL,
    target_price REAL,
    risk_reward REAL,
    quality_score REAL,
    confidence TEXT,
    num_edges INTEGER,
    edges_fired TEXT,
    strategy TEXT DEFAULT 'swing',
    position_size_usd REAL,
    shares INTEGER,
    risk_amount REAL,
    expected_return_pct REAL,
    expected_timeframe TEXT,
    reasoning TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    order_id TEXT,
    decided_at TEXT
)
```

**JOIN key:** `paper_trades.proposal_id  →  proposals.id`
(1:1; `paper_trades` has `UNIQUE(proposal_id)`). Used as `LEFT JOIN proposals p ON pt.proposal_id = p.id`.

> proposals has **no `direction`, `archetype`, `dim_scores`, `daily_bias`,
> `weekly_bias`, `rs_vs_spy`, or pivot columns.** (relevant to §3e)

---

## 2. TWO REAL ROWS (verbatim JSON, with joined proposal)

### 2a. CLOSED legacy trade WITH `r_multiple` populated
`-- SQL: select * from paper_trades where status='closed' and r_multiple IS NOT NULL order by id desc limit 1`
```json
{"id": 78, "proposal_id": 269, "symbol": "SRPT", "account_type": "personal", "strategy": "short_term", "direction": "long", "confidence": "LOW", "num_edges": 3, "edges_fired": "downtrend_break, weekly_pivot, rsi_room", "sector_name": "Biotechnology", "entry_price": 18.950000762939453, "stop_loss": 18.0025, "target_price": 20.2765, "expected_timeframe": "1-2 days", "entry_date": "2026-07-11T00:15:38.449228+00:00", "max_hold_days": 4, "status": "closed", "exit_price": 20.2765, "exit_date": "2026-07-11T05:17:51.219825+00:00", "return_pct": 7.0, "outcome": "win", "book": null, "source": null, "archetype": null, "timeframe_band": null, "entry_type": null, "pattern": null, "rs_vs_spy": null, "compression_tf": null, "planned_rr": null, "process_grade": null, "process_score": null, "process_flags": null, "process_notes": null, "shares": null, "position_value": null, "r_multiple": 1.4, "pnl_usd": null}
```
`-- SQL: select * from proposals where id=269`
```json
{"id": 269, "created_at": "2026-07-11T00:15:38.441047+00:00", "account_type": "personal", "symbol": "SRPT", "sector_name": "Biotechnology", "entry_price": 18.950000762939453, "stop_loss": 18.0025, "target_price": 20.2765, "risk_reward": 1.4, "quality_score": 4.0, "confidence": "LOW", "num_edges": 3, "edges_fired": "downtrend_break, weekly_pivot, rsi_room", "strategy": "short_term", "position_size_usd": 1042.25, "shares": 55, "risk_amount": 52.11, "expected_return_pct": 7.0, "expected_timeframe": "1-2 days", "reasoning": "SRPT (Biotechnology) SHORT-TERM LOW (3 edges): downtrend_break, weekly_pivot, rsi_room. Entry 18.950000762939453 / stop 18.0025 / target 20.2765 = 1.4:1, ~7.0% in 1-2 days.", "status": "pending", "order_id": null, "decided_at": null}
```

### 2b. CLOSED legacy trade WHERE `r_multiple` IS NULL
`-- SQL: select * from paper_trades where status='closed' and r_multiple IS NULL order by id desc limit 1`
```json
{"id": 39, "proposal_id": 109, "symbol": "INO", "account_type": "agentic", "strategy": "short_term", "direction": "long", "confidence": "LOW", "num_edges": 3, "edges_fired": "bb_squeeze, macd_4h, rsi_room", "sector_name": "Biotechnology", "entry_price": 1.190000057220459, "stop_loss": 1.1305, "target_price": 1.27, "expected_timeframe": "1-2 days", "entry_date": "2026-07-10T02:56:07.448341+00:00", "max_hold_days": 4, "status": "closed", "exit_price": 1.1305, "exit_date": "2026-07-11T00:06:56.373579+00:00", "return_pct": -5.0, "outcome": "loss", "book": null, "source": null, "archetype": null, "timeframe_band": null, "entry_type": null, "pattern": null, "rs_vs_spy": null, "compression_tf": null, "planned_rr": null, "process_grade": null, "process_score": null, "process_flags": null, "process_notes": null, "shares": null, "position_value": null, "r_multiple": null, "pnl_usd": null}
```
`-- SQL: select * from proposals where id=109`
```json
{"id": 109, "created_at": "2026-07-10T02:56:07.440007+00:00", "account_type": "agentic", "symbol": "INO", "sector_name": "Biotechnology", "entry_price": 1.190000057220459, "stop_loss": 1.1305, "target_price": 1.27, "risk_reward": 1.34, "quality_score": 3.71, "confidence": "LOW", "num_edges": 3, "edges_fired": "bb_squeeze, macd_4h, rsi_room", "strategy": "short_term", "position_size_usd": 149.94, "shares": 126, "risk_amount": 7.5, "expected_return_pct": 6.72, "expected_timeframe": "1-2 days", "reasoning": "INO (Biotechnology) SHORT-TERM LOW (3 edges): bb_squeeze, macd_4h, rsi_room. Entry 1.190000057220459 / stop 1.1305 / target 1.27 = 1.34:1, ~6.72% in 1-2 days.", "status": "expired", "order_id": null, "decided_at": null}
```

> Why one has `r_multiple` and one doesn't: **id 78 (SRPT) closed 2026-07-11T05:17:51**,
> just after the new `close_paper_trade` deployed (05:17:49) → it computed R.
> **id 39 (INO) closed 2026-07-11T00:06:56**, before deploy, by the old close path → NULL.
> Both proposals carry all the geometry (`entry_price/stop_loss/return_pct` via the
> trade), so R is backfillable for the NULL row (see §3c). Note the joined proposal
> `status` (`pending`/`expired`) is the *proposal* lifecycle, independent of the paper-trade close.

---

## 3. FIELD FACTS

### a. Exit/close/fill price on closed trades
**Yes — column `exit_price`** (and `exit_date`). Realized return is `return_pct`.
`-- SQL: select count(exit_price) exit_price_nn, count(return_pct) return_pct_nn, count(*) closed_total from paper_trades where status='closed'`
→ `{"exit_price_nn": 24, "return_pct_nn": 24, "closed_total": 24}` (both 24/24 on closed).
There is **no `fill_price`** and **no `exit_reason`** column.

### b. Direction / side column
**Yes — column `direction`** (`'long'`/`'short'`, default `'long'`), fully populated.
`-- SQL: select direction, count(*) n from paper_trades group by direction`
→ `long: 64`, `short: 14`. (So the "if not, count stop>entry" fallback isn't needed.)
Cross-check, closed shorts by geometry:
`-- SQL: select symbol, direction, entry_price, stop_loss from paper_trades where status='closed' and stop_loss>entry_price`
→ `LBRT, TECK, DVN, EOG, MAXN` — all have `direction='short'` (consistent).

### c. Code path that wrote `r_multiple` (reuse for backfill)
`-- SQL: select count(r_multiple) from paper_trades` → 10/78.
Written by **`database.Database.close_paper_trade`** (verbatim — the math is lines
`risk_pct`/`r_multiple`):
```python
def close_paper_trade(self, trade_id: int, exit_price: float, return_pct: float,
                      outcome: str, status: str) -> None:
    with self._conn() as conn:
        row = conn.execute(
            "SELECT entry_price, stop_loss, direction, shares FROM paper_trades WHERE id = ?",
            (trade_id,)).fetchone()
        r_multiple = pnl_usd = None
        if row:
            entry, stop = row["entry_price"], row["stop_loss"]
            is_short = row["direction"] == "short"
            # R-multiple: realized return divided by the planned risk-to-stop
            # (both as % of entry). +1R = made exactly what was risked; -1R = full stop.
            risk_pct = (abs(entry - stop) / entry * 100) if entry else 0.0
            if risk_pct > 0:
                r_multiple = round(return_pct / risk_pct, 2)
            if row["shares"]:
                per_share = (entry - exit_price) if is_short else (exit_price - entry)
                pnl_usd = round(row["shares"] * per_share, 2)
        conn.execute(
            """UPDATE paper_trades
               SET status = ?, outcome = ?, exit_price = ?, return_pct = ?, exit_date = ?,
                   r_multiple = ?, pnl_usd = ?
               WHERE id = ?""",
            (status, outcome, round(exit_price, 4), round(return_pct, 2), _now(),
             r_multiple, pnl_usd, trade_id),
        )
```
**Backfill formula (verbatim from above):** `r_multiple = round(return_pct / (abs(entry_price - stop_loss) / entry_price * 100), 2)`. Verified against id 78: `abs(18.95-18.0025)/18.95*100 = 5.0%`, `7.0/5.0 = 1.4` ✓.
`pnl_usd` is NOT backfillable for legacy — it needs `shares`, which is NULL on paper_trades legacy rows (the proposal has `shares`, but the close function reads `paper_trades.shares`).

### d. Write-time grading path — is OUTCOME an input? **NO.**
The grade is computed **at open** and is **outcome-independent**. `grade_fields`
is called from `open_from_proposal` (open time); it receives the `analysis` dict
only — no `exit_price`, `return_pct`, `outcome`, or `pnl` is passed in or read.

**`paper_trader.grade_fields`** (write-time wrapper; verbatim):
```python
_ENTRY_TYPE = {
    "trending_pullback_to_pivot": "pullback-zone",
    "reversal": "reversal-break",
    "breakout_continuation": "breakout/retest",
}
# fields an analysis MUST carry to be gradeable; missing => UNGRADED (bright flag)
_GRADEABLE_FIELDS = ("archetype", "dim_scores", "rs_vs_spy")

def grade_fields(analysis: dict | None, *, model: str, sector_name: str | None,
                 config: dict | None, db: Database) -> dict:
    analysis = analysis or {}
    patterns = analysis.get("patterns") or []
    base = {
        "archetype": analysis.get("archetype"),
        "timeframe_band": analysis.get("timeframe_band"),
        "entry_type": _ENTRY_TYPE.get(analysis.get("archetype"), None),
        "pattern": "; ".join(patterns) if patterns else None,
        "rs_vs_spy": analysis.get("rs_vs_spy"),
        "compression_tf": analysis.get("compression_tf"),
        "planned_rr": analysis.get("risk_reward"),
    }
    if any(analysis.get(k) is None for k in _GRADEABLE_FIELDS):
        base.update({
            "process_grade": "UNGRADED", "process_score": None,
            "process_flags": json.dumps(["ungraded_missing_fields"]),
            "process_notes": "UNGRADED -- engine did not emit archetype/dim_scores/rs_vs_spy.",
        })
        return base
    leaders = {s.upper() for s in (config or {}).get("sector_leaders", [])}
    is_leader = str(analysis.get("symbol", "")).upper() in leaders
    sector_score = None
    if sector_name:
        for r in db.get_latest_sector_rankings():
            if r.get("sector_name") == sector_name:
                sector_score = r.get("composite_score")
                break
    g = process_grader.grade(analysis, model=model, sector_score=sector_score,
                             is_sector_leader=is_leader)
    base.update({
        "process_grade": g["grade"], "process_score": g["score"],
        "process_flags": json.dumps(g["flags"]), "process_notes": g["notes"],
    })
    return base
```

**`process_grader.grade`** (the scorer; verbatim — note it reads only setup fields,
never outcome/P&L):
```python
_WEIGHTS = {                    # (top of module; sums to 100)
    "entry_discipline": 26, "timeframe_confluence": 18, "confluence_breadth": 16,
    "stop_at_structure": 14, "rr_quality": 12, "sector_alignment": 8, "rel_strength": 6,
}
def _letter(score: float) -> str:
    if score >= 88: return "A"
    if score >= 78: return "B"
    if score >= 68: return "C"
    if score >= 55: return "D"
    return "F"

def grade(analysis: dict[str, Any], *, model: str = "swing",
          sector_score: Optional[float] = None,
          is_sector_leader: bool = False,
          min_stop_pct: float = 0.025) -> dict[str, Any]:
    direction = analysis.get("direction", "long")
    entry = analysis.get("entry_price") or analysis.get("current_price") or 0.0
    stop = analysis.get("stop_loss") or 0.0
    rr = float(analysis.get("risk_reward") or 0.0)
    archetype = analysis.get("archetype", "trending_pullback_to_pivot")
    support = analysis.get("nearest_support")
    patterns = analysis.get("patterns") or []
    dim_scores = analysis.get("dim_scores") or {}
    num_edges = int(analysis.get("num_edges") or 0)
    daily_bias = analysis.get("daily_bias", "NEUTRAL")
    weekly_bias = analysis.get("weekly_bias", "NEUTRAL")
    compression_dir = analysis.get("compression_dir")
    rs_vs_spy = analysis.get("rs_vs_spy")
    bb_breakout = bool((analysis.get("details") or {}).get("bb_percent_b", 0) and
                       analysis.get("bb_position") == "NEAR_UPPER")
    floor = _RR_FLOOR.get(model, 1.5)
    subs: dict[str, float] = {}
    flags: list[str] = []
    def run(key, result):
        score, fl = result
        subs[key] = round(score, 3); flags.extend(fl)
    run("rr_quality", _rr_quality(rr, floor))
    run("entry_discipline", _entry_discipline(archetype, direction, entry, support,
                                              patterns, compression_dir, bb_breakout))
    run("stop_at_structure", _stop_at_structure(direction, entry, stop, support, min_stop_pct))
    run("confluence_breadth", _confluence_breadth(dim_scores, num_edges))
    run("timeframe_confluence", _timeframe_confluence(direction, daily_bias, weekly_bias))
    run("sector_alignment", _sector_alignment(direction, sector_score, is_sector_leader))
    run("rel_strength", _rel_strength(direction, rs_vs_spy))
    score = round(sum(_WEIGHTS[k] * subs[k] for k in _WEIGHTS), 1)
    letter = _letter(score)
    # ... note string ...
    return {"grade": letter, "score": score, "flags": flags,
            "notes": note, "subscores": subs, "archetype": archetype}
```
(Sub-scorers `_rr_quality/_entry_discipline/_stop_at_structure/_confluence_breadth/_timeframe_confluence/_sector_alignment/_rel_strength` live in `src/process_grader.py`; none take outcome/P&L.)

### e. Grader inputs & legacy recoverability via the proposal JOIN
Inputs `grade()` reads (from the `analysis` dict) + the two context args:

| Input | Recoverable for legacy? | From where |
|---|---|---|
| `entry_price`, `stop_loss` | ✅ | `paper_trades` (and `proposals`) |
| `risk_reward` | ✅ | `proposals.risk_reward` (JOIN) |
| `num_edges` | ✅ | `paper_trades.num_edges` / `proposals.num_edges` |
| `direction` | ✅ | `paper_trades.direction` (NOT in `proposals`) |
| `sector_score` (via `sector_name`) | ✅ | `sector_name` on both → live `sector_rankings` |
| `is_sector_leader` (symbol vs config list) | ✅ | `symbol` + `config.sector_leaders` |
| **`archetype`** | ❌ | stored nowhere for legacy |
| **`dim_scores`** | ❌ | never persisted (only `quality_score` scalar is) |
| **`rs_vs_spy`** | ❌ | not stored for legacy |
| `nearest_support` (pivot) | ❌ | not stored |
| `daily_bias`, `weekly_bias` | ❌ | not stored per-trade (`technical_analysis` table has bias but is keyed by symbol+timestamp with **no proposal_id/trade link**) |
| `patterns`, `compression_dir` | ❌ | not stored |

**Blocking fact:** `grade_fields` requires **`archetype`, `dim_scores`, `rs_vs_spy`**
(`_GRADEABLE_FIELDS`) or it returns `UNGRADED`. All three are in the ❌ column →
**legacy trades cannot be re-graded from stored data**; a backfill could recover
R:R / quality / edges / rationale (for display) but not a real letter grade.

---

## 4. SCORING MODULE (verbatim)

Buy-engine `quality_score` (0–10) — five capped dimensions summed
(`src/technical_analyzer.py`):
```python
_DIM_CAP = 2.0
_DIMENSIONS = ("structure", "momentum", "volatility", "volume", "rel_strength")

def _new_dims():
    return {d: [] for d in _DIMENSIONS}

def _aggregate_dims(dims, caps=None):
    caps = caps or {}
    dim_scores = {d: round(min(caps.get(d, _DIM_CAP), sum(s["points"] for s in subs)), 2)
                  for d, subs in dims.items()}
    quality = round(sum(dim_scores.values()), 2)
    fired = [s["name"] for subs in dims.values() for s in subs if s["fired"]]
    return dim_scores, quality, fired, len(fired)
```
Coiling `coil_score` (0–10) — weighted edge ratio (line 636):
```python
coil_score = round(10 * earned / possible, 2) if possible else 0.0
```

### Every confluence flag the scanner can emit
`-- grep: rg -n 'sig\("|add\("' src/technical_analyzer.py` (flag = 2nd arg)

**swing `analyze`** (`sig(dim, name, …)`): `mtf_structure`, `ema_9_21`,
`ema_20_50`, `ema_50_200`, `macd_daily`, `macd_mtf_confluence`, `momentum_roc`,
`mfi_regime`, `squeeze`, `bb_position`, `compression_resolve_up`,
`volume_confirmation`, `relative_volume`, `buying_pressure`, `volume_profile`,
`rs_vs_spy_20`, `rs_vs_spy_60`, `chart_pattern`, `demand_zone_entry`

**`analyze_short_term`**: `bb_squeeze`, `compression_resolve_up`, `macd_4h`,
`ema_9_21`, `ema_20_50`, `mfi_room`, `downtrend_break`, `weekly_pivot`,
`inside_day_macd`, `volume_surge`, `rs_vs_spy_20`, `rs_vs_spy_60`

**`analyze_coiling`** (`add(name, …)`): `monthly_squeeze`, `quarterly_squeeze`,
`weekly_squeeze`, `daily_squeeze`, `flat_price`, `accumulation`, `volume_building`,
`mfi_room`, `base_intact`

**`analyze_downside`**: `mtf_downtrend`, `ema_9_21_down`, `ema_20_50_down`,
`ema_50_200_down`, `macd_daily_bear`, `macd_mtf_bear`, `momentum_down`, `mfi_weak`,
`bollinger_breakdown`, `bollinger_rejection`, `compression_resolve_down`,
`volume_confirmation`, `relative_volume`, `distribution`, `rs_vs_spy_20`, `rs_vs_spy_60`

> Legacy `edges_fired` strings still contain the pre-refactor name `rsi_room`
> (see the two rows in §2); current code emits `mfi_room`.

---

## 5. UNIVERSE (verbatim)

`-- file: config/universe.json` (path from `config.universe.sector_tickers_file`; loaded by `src/sector_analyzer.py`)
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
> Ambiguity: two `etf` values repeat (`IGV` for Software + AI&Data-Infra; `XLV`
> for Healthcare + Obesity&GLP-1), and several tickers appear in multiple sectors
> (e.g. NVDA, AVGO) — relevant to any overlap/liquidity audit.

---

## 6. CLOSE FUNCTIONS (verbatim, reference only)

**`paper_trader.resolve_open`** (daily-bar replay; exit-reason logic = the
hit_stop/hit_target branches):
```python
def resolve_open(db: Database) -> dict[str, int]:
    open_trades = db.get_paper_trades(status="open")
    summary = {"checked": len(open_trades), "wins": 0, "losses": 0, "expired": 0, "still_open": 0}
    for t in open_trades:
        try:
            entry_dt = datetime.fromisoformat(t["entry_date"])
        except (ValueError, TypeError):
            continue
        entry = t["entry_price"]; stop = t["stop_loss"]; target = t["target_price"]
        now = datetime.now(timezone.utc); days_held = (now - entry_dt).days
        try:
            hist = yf.Ticker(t["symbol"]).history(
                start=entry_dt.date().isoformat(), interval="1d", auto_adjust=True)
        except Exception as exc:
            logger.debug("resolve %s failed: %s", t["symbol"], exc)
            summary["still_open"] += 1; continue
        if hist is None or hist.empty:
            summary["still_open"] += 1; continue
        is_short = t.get("direction") == "short"
        def ret_at(exit_price: float) -> float:
            return ((entry - exit_price) if is_short else (exit_price - entry)) / entry * 100
        resolved = False
        for _, bar in hist.iterrows():
            if is_short:
                hit_target = bar["Low"] <= target; hit_stop = bar["High"] >= stop
            else:
                hit_target = bar["High"] >= target; hit_stop = bar["Low"] <= stop
            if hit_stop and hit_target:  # both same bar -> assume stop first
                db.close_paper_trade(t["id"], stop, ret_at(stop), "loss", "closed")
                summary["losses"] += 1; resolved = True; break
            if hit_target:
                db.close_paper_trade(t["id"], target, ret_at(target), "win", "closed")
                summary["wins"] += 1; resolved = True; break
            if hit_stop:
                db.close_paper_trade(t["id"], stop, ret_at(stop), "loss", "closed")
                summary["losses"] += 1; resolved = True; break
        if resolved: continue
        # timed out -> close at the latest close, count by sign of return
        if days_held >= (t["max_hold_days"] or 21):
            last_close = float(hist["Close"].iloc[-1]); ret = ret_at(last_close)
            db.close_paper_trade(t["id"], last_close, ret, "win" if ret > 0 else "loss", "closed")
            summary["expired"] += 1
        else:
            summary["still_open"] += 1
    logger.info("Paper-trade resolution: %s", summary)
    return summary
```

**`scheduler.close_on_live_cross`** (Alpaca live-price cross):
```python
def close_on_live_cross(db, alpaca) -> int:
    if not getattr(alpaca, "enabled", False):
        return 0
    open_trades = db.get_paper_trades(status="open")
    if not open_trades:
        return 0
    prices = alpaca.latest_prices(sorted({t["symbol"] for t in open_trades}))
    closed = 0
    for t in open_trades:
        lp = prices.get(t["symbol"], {}).get("price")
        if lp is None:
            continue
        is_short = t.get("direction") == "short"
        entry, stop, tgt = t["entry_price"], t["stop_loss"], t["target_price"]
        hit_stop = lp >= stop if is_short else lp <= stop
        hit_tgt = lp <= tgt if is_short else lp >= tgt
        exit_price, outcome = (None, None)
        if hit_stop:                              # stop checked first (conservative)
            exit_price, outcome = stop, "loss"
        elif hit_tgt:
            exit_price, outcome = tgt, "win"
        if exit_price is not None:
            ret = ((entry - exit_price) if is_short else (exit_price - entry)) / entry * 100
            db.close_paper_trade(t["id"], exit_price, round(ret, 2), outcome, "closed")
            logger.info("LIVE-CLOSE %s %s @ %.4f (%s) live=%.4f",
                        t["symbol"], outcome, exit_price, t.get("direction", "long"), lp)
            closed += 1
    return closed
```
> For a derived `exit_reason`: both functions already branch on `hit_stop`
> (first) vs `hit_target`; `resolve_open` also has a third path (`days_held >=
> max_hold_days` → "timeout"). `close_on_live_cross` has only stop/target
> (no timeout branch).

---

## 7. DASHBOARD DATA PATH (Track Record)

**Endpoint the Track Record page reads:** `GET /api/log/algo`
(`src/api_server.py`), which calls `DB.get_algo_trades()`. Filtering (open/closed/all)
is currently **client-side** in `renderTrackRecord`; the endpoint accepts an
optional `status` query param but the page passes none. New server-side
sort/filter params would go into `get_algo_log` + `get_algo_trades`.

**`get_algo_log`** (transform):
```python
@app.get("/api/log/algo")
def get_algo_log(status: Optional[str] = None) -> dict[str, Any]:
    trades = DB.get_algo_trades(status=status)
    for t in trades:
        t["risk_reward"] = t.get("planned_rr") if t.get("planned_rr") is not None \
            else t.get("proposal_risk_reward")
        t["quality_score"] = t.get("proposal_quality_score")
        if not t.get("edges_fired"):
            t["edges_fired"] = t.get("proposal_edges_fired")
        t["reasoning"] = t.get("proposal_reasoning")
        t["legacy"] = t.get("process_grade") is None
    graded = sum(1 for t in trades if t.get("process_grade") and t["process_grade"] != "UNGRADED")
    ungraded = sum(1 for t in trades if t.get("process_grade") == "UNGRADED")
    legacy = sum(1 for t in trades if t["legacy"])
    return {"count": len(trades), "graded": graded, "ungraded": ungraded,
            "legacy": legacy, "trades": trades}
```

**`Database.get_algo_trades`** (the query — this is where a WHERE/ORDER BY param would be added):
```python
def get_algo_trades(self, status: Optional[str] = None) -> list[dict[str, Any]]:
    query = """
        SELECT pt.*,
               p.risk_reward   AS proposal_risk_reward,
               p.quality_score AS proposal_quality_score,
               p.edges_fired   AS proposal_edges_fired,
               p.num_edges     AS proposal_num_edges,
               p.reasoning     AS proposal_reasoning
        FROM paper_trades pt
        LEFT JOIN proposals p ON pt.proposal_id = p.id
        WHERE (pt.book = 'algo' OR pt.book IS NULL)
    """
    params: list[Any] = []
    if status:
        query += " AND pt.status = ?"
        params.append(status)
    query += " ORDER BY pt.entry_date DESC"
    with self._conn() as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]
```

**Frontend loader** (`src/static/app.js`): `loadAlgo()` fetches the endpoint,
caches `lastAlgoData`, and renders. The client-side filter lives in
`renderTrackRecord` via module var `trackFilter` (`all|open|closed`) + `setTrackFilter`.
```javascript
async function loadAlgo() {
  try {
    await refreshLiveIndex();
    const d = await fetchJSON("/api/log/algo");
    algoIndex = {};
    (d.trades || []).forEach(t => algoIndex[t.id] = t);
    lastAlgoData = d;
    renderIdeasFeed(d);
    renderTrackRecord(d);
  } catch (e) {
    const el = $("ideas-feed"); if (el) el.innerHTML = `<p class="muted">${e.message}</p>`;
  }
}
function setTrackFilter(f) { trackFilter = f; renderTrackRecord(lastAlgoData); }
// renderTrackRecord: const rows = trackFilter === 'all' ? trades : trades.filter(t => t.status === trackFilter);
```

---

## 8. GAPS TABLE (verbatim from CURRENT_STATE.md)

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
*Verbatim extract; DB values from live SQLite over read-only SSH. No files other than this were created or modified.*
