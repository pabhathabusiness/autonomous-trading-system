"""
SQLite persistence layer for the autonomous trading system.

Every other module reads/writes through the Database class rather than
touching sqlite3 directly, so the schema lives in exactly one place.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_type TEXT UNIQUE NOT NULL,
    starting_balance REAL NOT NULL,
    current_balance REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS market_regime (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    symbol TEXT NOT NULL,
    regime TEXT NOT NULL,
    price REAL,
    trend_30d REAL,
    trend_10d REAL,
    trend_5d REAL,
    trend_1d REAL,
    rsi REAL,
    condition TEXT,
    composite_score REAL
);

CREATE TABLE IF NOT EXISTS sector_rankings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    sector_name TEXT NOT NULL,
    etf_symbol TEXT NOT NULL,
    perf_1d REAL,
    perf_5d REAL,
    perf_10d REAL,
    perf_30d REAL,
    composite_score REAL,
    rank INTEGER
);

CREATE TABLE IF NOT EXISTS screened_stocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    account_type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    sector_name TEXT,
    price REAL,
    volume INTEGER,
    market_cap REAL,
    revenue REAL,
    rev_to_mcap_ratio REAL,
    fundamentals_score REAL
);

CREATE TABLE IF NOT EXISTS technical_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    symbol TEXT NOT NULL,
    quality_score REAL,
    structure_bias TEXT,
    daily_bias TEXT,
    weekly_bias TEXT,
    monthly_bias TEXT,
    confluence_score REAL,
    macd_signal TEXT,
    bb_position TEXT,
    rsi REAL,
    nearest_support REAL,
    nearest_resistance REAL,
    details_json TEXT
);

CREATE TABLE IF NOT EXISTS proposals (
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
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id INTEGER,
    account_type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL,
    entry_price REAL,
    exit_price REAL,
    entry_time TEXT,
    exit_time TEXT,
    pnl REAL,
    pnl_pct REAL,
    status TEXT NOT NULL DEFAULT 'open',
    order_id TEXT,
    FOREIGN KEY(proposal_id) REFERENCES proposals(id)
);

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    quantity REAL,
    avg_price REAL,
    current_price REAL,
    market_value REAL,
    unrealized_pnl REAL,
    unrealized_pnl_pct REAL,
    updated_at TEXT,
    UNIQUE(account_type, symbol)
);

CREATE TABLE IF NOT EXISTS performance_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_type TEXT NOT NULL,
    date TEXT NOT NULL,
    total_value REAL,
    cash REAL,
    daily_pnl REAL,
    daily_pnl_pct REAL,
    total_pnl REAL,
    total_pnl_pct REAL,
    win_rate REAL,
    num_trades INTEGER,
    num_wins INTEGER,
    num_losses INTEGER,
    UNIQUE(account_type, date)
);

CREATE TABLE IF NOT EXISTS paper_trades (
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
    outcome TEXT,
    UNIQUE(proposal_id)
);

CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT UNIQUE NOT NULL,
    note TEXT,
    added_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS news_cache (
    key TEXT PRIMARY KEY,
    payload_json TEXT,
    fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS mtf_conflicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    symbol TEXT NOT NULL,
    strategy TEXT,
    direction TEXT,
    band TEXT,
    biases_json TEXT,
    label TEXT,
    note TEXT
);

-- Addendum 7: append-only news store (no auto-delete -- needed for the 30d
-- trending baseline and to reconstruct "what news was visible when this trade
-- triggered". Dedup by headline hash.)
CREATE TABLE IF NOT EXISTS news_items (
    hash TEXT PRIMARY KEY,
    symbol TEXT,
    headline TEXT,
    source TEXT,
    url TEXT,
    published_ts INTEGER,      -- unix seconds (from Finnhub 'datetime')
    first_seen TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_news_items_ts ON news_items(published_ts);

-- Addendum 2 (quarantined small-cap lane). Daily-refreshed screen snapshot.
-- Finnhub-sourced fields (float_shares, so_proxy, dilution_risk, upside_to_target_pct,
-- has_options/options_liquid/has_leaps) stay NULL until FINNHUB_KEY is set + verified;
-- OHLC-derived fields populate from yfinance now.
CREATE TABLE IF NOT EXISTS smallcap_universe (
    symbol TEXT PRIMARY KEY,
    updated_at TEXT,
    price REAL,
    price_tier TEXT,            -- special | low | sub2 | deep (A3 Part 2)
    exchange TEXT,
    sector_name TEXT,
    float_shares REAL,          -- millions (raw SO)
    float_est REAL,             -- SO-proxy 0.85 haircut, tier display only
    so_proxy INTEGER,           -- 1 = shares-outstanding proxy, not true float
    float_tier TEXT,            -- runner | low | mid | standard | large
    avg_dollar_vol_20d REAL,
    rel_vol REAL,               -- v1 daily
    bb_percentile REAL,
    daily_compression INTEGER,
    compression_extreme INTEGER,
    squeeze_days INTEGER,
    up_wow INTEGER,
    consecutive_up_weeks INTEGER,
    dilution_risk INTEGER,
    upside_to_target_pct REAL,
    has_options INTEGER,
    options_liquid INTEGER,
    has_leaps INTEGER,
    signals_json TEXT
);

-- Auditable hard-exclusion list. Names exit only by aging out of the criteria.
CREATE TABLE IF NOT EXISTS smallcap_deathwatch (
    symbol TEXT PRIMARY KEY,
    reason TEXT NOT NULL,       -- reverse_split_18mo | serial_reverse_split | going_concern
                               -- | share_dilution_100pct | sub_dollar_20d | permanent
    detail TEXT,
    added_at TEXT NOT NULL,
    last_checked TEXT
);

-- B3 risk state: one row per account. Drives the daily-loss halt (-2% of
-- day-start equity) and the drawdown kill-switch (-10% below equity HWM).
-- Persisted so a crash-restart cannot resume trading while halted.
CREATE TABLE IF NOT EXISTS risk_state (
    account_type TEXT PRIMARY KEY,
    equity_high_water_mark REAL,
    day_key TEXT,                 -- YYYY-MM-DD (ET) baseline for the daily-loss line
    day_start_equity REAL,
    realized_pnl_today REAL DEFAULT 0,
    halted INTEGER DEFAULT 0,     -- 0/1 global halt for this account
    halt_reason TEXT,             -- daily_loss | drawdown | manual
    halted_at TEXT,
    updated_at TEXT
);

-- B1 fill event log: partial fills / rejects / cancels captured as discrete
-- events. The paper_trades columns carry the summary; this is the audit trail.
CREATE TABLE IF NOT EXISTS order_fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER,             -- FK -> paper_trades.id
    broker_order_id TEXT,
    leg TEXT,                     -- entry | stop | target
    event_type TEXT,              -- submitted | accepted | partial_fill | fill | reject | cancel
    qty REAL,
    price REAL,
    ts TEXT,
    raw_json TEXT
);

-- B1 sim-vs-real: real fills with the SIM numbers beside the REAL numbers, so
-- we can measure how much the internal simulation was lying over the first ~30
-- real trades. (The paper_trades row keeps sim pnl/return/R untouched; the
-- real_* columns hold the broker-fill truth.)
CREATE VIEW IF NOT EXISTS sim_vs_real AS
SELECT id, symbol, lane, book, account_type, entry_date, exit_date, status,
       submitted_at, is_real,
       entry_price   AS sim_entry,
       fill_price    AS real_entry,
       slippage_bps,
       exit_price    AS sim_exit,
       exit_fill_price AS real_exit,
       exit_slippage_bps,
       pnl_usd       AS sim_pnl_usd,     real_pnl_usd,
       return_pct    AS sim_return_pct,  real_return_pct,
       r_multiple    AS sim_r_multiple,  real_r_multiple,
       was_rejected, partial_fill, gap_through_stop,
       time_to_fill, exit_time_to_fill
FROM paper_trades
WHERE is_real = 1
ORDER BY submitted_at DESC;
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, db_path: str = "data/trading_system.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        # 15s busy wait so the background small-cap universe build (many quick
        # upserts) doesn't raise "database is locked" against concurrent reads
        conn.execute("PRAGMA busy_timeout = 15000")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA)
            self._migrate(conn)

    @staticmethod
    def _migrate(conn) -> None:
        """Additively add columns introduced after the first schema so
        existing databases keep working without a manual drop."""
        migrations = {
            "proposals": [
                ("confidence", "TEXT"),
                ("num_edges", "INTEGER"),
                ("edges_fired", "TEXT"),
                ("strategy", "TEXT"),
                # Lane 1.4: direction at proposal time (downside=short, else long)
                ("direction", "TEXT"),
                # Phase 4a: event risk at proposal time, from the earnings cache
                ("days_to_earnings", "INTEGER"),
                # Lane 4: regime + MTF read + RS stamped at proposal time so all
                # future trades are fully gradable with zero gaps
                ("market_regime", "TEXT"),
                ("mtf_alignment", "TEXT"),
                ("rs_vs_spy", "REAL"),
            ],
            "paper_trades": [
                ("direction", "TEXT"),
                # --- book / source (Log A "mine" vs Log B "algo") ---
                ("book", "TEXT"),
                ("source", "TEXT"),
                # --- classification / logged context (from analyze()) ---
                ("archetype", "TEXT"),
                ("timeframe_band", "TEXT"),
                ("entry_type", "TEXT"),
                ("pattern", "TEXT"),
                ("rs_vs_spy", "REAL"),
                ("compression_tf", "TEXT"),
                ("planned_rr", "REAL"),
                # --- process grade (outcome-independent) ---
                ("process_grade", "TEXT"),
                ("process_score", "REAL"),
                ("process_flags", "TEXT"),
                ("process_notes", "TEXT"),
                # --- dollar accounting + R (filled at close) ---
                ("shares", "REAL"),
                ("position_value", "REAL"),
                ("r_multiple", "REAL"),
                ("pnl_usd", "REAL"),
                # --- Lane 1 backfills (derived post-close; close functions untouched) ---
                ("exit_reason", "TEXT"),   # stop | target | timeout | unknown
                ("mae_r", "REAL"),         # max adverse excursion, in R
                ("mfe_r", "REAL"),         # max favorable excursion, in R
                # --- Lane 2: retro track (legacy) + quadrants (all closed) ---
                ("retro_grade", "TEXT"),   # A..F, shown as R-A..R-F (outline badge)
                ("retro_score", "REAL"),   # 0-100 rubric score behind retro_grade
                ("quadrant", "TEXT"),      # skill_win | lucky_win | good_loss | bad_loss
                # --- Lane 4: regime + MTF context at open ---
                ("market_regime", "TEXT"),
                ("mtf_alignment", "TEXT"),
                # --- Addendum 2: quarantined small-cap lane tag ---
                ("lane", "TEXT"),   # runner | bounce | value | hailmary (book='smallcap' rows)
                ("lane_score", "REAL"),     # the lane rubric score at trigger
                ("trigger_json", "TEXT"),   # reasons/chips/catalyst snapshot
                # --- Addendum 3 / 6: multi-edge composite, price tier, hold band ---
                ("composite_score", "REAL"),   # 0-10 multi-edge composite at trigger
                ("price_tier", "TEXT"),        # special | low | sub2 | deep
                ("hold_band", "TEXT"),         # overnight | short | medium | position
                ("gap_pct", "REAL"),           # overnight band: (next open - prior close)/prior close
                ("hit_time_stop", "INTEGER"),  # band time-stop auto-close flag
                # --- B1: Alpaca paper order placement + FILL recording ---
                ("broker_order_id", "TEXT"),   # Alpaca bracket PARENT order id
                ("client_order_id", "TEXT"),   # deterministic idempotency key (dedupes retries)
                ("order_status", "TEXT"),       # submitted|accepted|partially_filled|filled|rejected|canceled
                ("submitted_at", "TEXT"),       # ISO ts the order was POSTed
                ("fill_price", "REAL"),         # actual avg entry fill (vs planned entry_price)
                ("filled_qty", "REAL"),         # shares actually filled
                ("slippage_bps", "REAL"),       # signed (fill-entry)/entry*1e4
                ("was_rejected", "INTEGER"),    # 0/1 broker rejected/errored
                ("partial_fill", "INTEGER"),    # 0/1 filled_qty < requested
                ("gap_through_stop", "INTEGER"),# 0/1 exit filled materially worse than stop
                ("time_to_fill", "REAL"),       # seconds submitted_at -> entry fill
                ("exit_fill_price", "REAL"),    # actual avg exit fill
                ("exit_slippage_bps", "REAL"),  # signed exit-side slippage vs planned level
                ("exit_time_to_fill", "REAL"),  # seconds to the exit fill
                # --- B1: real vs sim (sim numbers stay in pnl_usd/return_pct/r_multiple) ---
                ("is_real", "INTEGER"),         # 1 = backed by a real Alpaca fill, 0/NULL = pure sim
                ("real_pnl_usd", "REAL"),       # realized $ from real fills
                ("real_return_pct", "REAL"),    # realized % from real fills
                ("real_r_multiple", "REAL"),    # realized R from real fills
            ],
            # Addendum 3: small-cap universe gains price tier + SO-proxy float estimate
            "smallcap_universe": [
                ("price_tier", "TEXT"),
                ("float_est", "REAL"),
            ],
        }
        for table, cols in migrations.items():
            existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            for name, coltype in cols:
                if name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {coltype}")

    # ---------------------------------------------------------------- accounts
    def seed_accounts(self, accounts_config: dict[str, dict[str, Any]]) -> None:
        with self._conn() as conn:
            for account_type, cfg in accounts_config.items():
                conn.execute(
                    """INSERT INTO accounts (account_type, starting_balance, current_balance, created_at)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(account_type) DO NOTHING""",
                    (account_type, cfg["starting_balance"], cfg["starting_balance"], _now()),
                )

    def get_account(self, account_type: str) -> Optional[sqlite3.Row]:
        with self._conn() as conn:
            return conn.execute(
                "SELECT * FROM accounts WHERE account_type = ?", (account_type,)
            ).fetchone()

    def update_account_balance(self, account_type: str, current_balance: float) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE accounts SET current_balance = ? WHERE account_type = ?",
                (current_balance, account_type),
            )

    # ------------------------------------------------------------ market regime
    def insert_market_regime(self, data: dict[str, Any]) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO market_regime
                   (timestamp, symbol, regime, price, trend_30d, trend_10d, trend_5d,
                    trend_1d, rsi, condition, composite_score)
                   VALUES (:timestamp, :symbol, :regime, :price, :trend_30d, :trend_10d,
                           :trend_5d, :trend_1d, :rsi, :condition, :composite_score)""",
                {"timestamp": _now(), **data},
            )
            return cur.lastrowid

    def get_latest_market_regime(self) -> Optional[dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM market_regime ORDER BY id DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None

    # ------------------------------------------------------------ sector ranks
    def insert_sector_rankings(self, rankings: Iterable[dict[str, Any]]) -> None:
        ts = _now()
        with self._conn() as conn:
            conn.executemany(
                """INSERT INTO sector_rankings
                   (timestamp, sector_name, etf_symbol, perf_1d, perf_5d, perf_10d,
                    perf_30d, composite_score, rank)
                   VALUES (:timestamp, :sector_name, :etf_symbol, :perf_1d, :perf_5d,
                           :perf_10d, :perf_30d, :composite_score, :rank)""",
                [{"timestamp": ts, **r} for r in rankings],
            )

    def get_latest_sector_rankings(self, limit: int = 40) -> list[dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute("SELECT MAX(timestamp) AS ts FROM sector_rankings").fetchone()
            if not row or not row["ts"]:
                return []
            rows = conn.execute(
                """SELECT * FROM sector_rankings WHERE timestamp = ?
                   ORDER BY rank ASC LIMIT ?""",
                (row["ts"], limit),
            ).fetchall()
            return [dict(r) for r in rows]

    # --------------------------------------------------------- screened stocks
    def insert_screened_stocks(self, stocks: Iterable[dict[str, Any]]) -> None:
        ts = _now()
        with self._conn() as conn:
            conn.executemany(
                """INSERT INTO screened_stocks
                   (timestamp, account_type, symbol, sector_name, price, volume,
                    market_cap, revenue, rev_to_mcap_ratio, fundamentals_score)
                   VALUES (:timestamp, :account_type, :symbol, :sector_name, :price,
                           :volume, :market_cap, :revenue, :rev_to_mcap_ratio,
                           :fundamentals_score)""",
                [{"timestamp": ts, **s} for s in stocks],
            )

    # ------------------------------------------------------ technical analysis
    def insert_technical_analysis(self, data: dict[str, Any]) -> int:
        payload = dict(data)
        payload["details_json"] = json.dumps(payload.get("details", {}))
        payload.pop("details", None)
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO technical_analysis
                   (timestamp, symbol, quality_score, structure_bias, daily_bias,
                    weekly_bias, monthly_bias, confluence_score, macd_signal,
                    bb_position, rsi, nearest_support, nearest_resistance, details_json)
                   VALUES (:timestamp, :symbol, :quality_score, :structure_bias,
                           :daily_bias, :weekly_bias, :monthly_bias, :confluence_score,
                           :macd_signal, :bb_position, :rsi, :nearest_support,
                           :nearest_resistance, :details_json)""",
                {"timestamp": _now(), **payload},
            )
            return cur.lastrowid

    # ------------------------------------------------------------- proposals
    def insert_proposal(self, data: dict[str, Any]) -> int:
        data = {**data, "created_at": data.get("created_at", _now()),
                "strategy": data.get("strategy", "swing")}
        # Lane 1.4: proposals carry direction at write time. Downside proposals
        # already pass direction='short'; every other strategy is a long. (The
        # 284 pre-existing rows were backfilled 2026-07-11 via the paper_trades
        # JOIN + this same strategy rule, proven conflict-free first.)
        data.setdefault("direction", "short" if data["strategy"] == "downside" else "long")
        # Phase 4a: event risk stamped at write time from the cached earnings
        # calendar (None when the cache is empty/keyless -- display handles it).
        data.setdefault("days_to_earnings", self.days_to_earnings(data.get("symbol")))
        # Lane 4: regime + MTF + RS context (generators supply; default NULL)
        for k in ("market_regime", "mtf_alignment", "rs_vs_spy"):
            data.setdefault(k, None)
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO proposals
                   (created_at, account_type, symbol, sector_name, entry_price,
                    stop_loss, target_price, risk_reward, quality_score,
                    confidence, num_edges, edges_fired, strategy, direction,
                    days_to_earnings, market_regime, mtf_alignment, rs_vs_spy,
                    position_size_usd, shares, risk_amount,
                    expected_return_pct, expected_timeframe, reasoning, status)
                   VALUES (:created_at, :account_type, :symbol, :sector_name,
                           :entry_price, :stop_loss, :target_price, :risk_reward,
                           :quality_score, :confidence, :num_edges, :edges_fired,
                           :strategy, :direction, :days_to_earnings,
                           :market_regime, :mtf_alignment, :rs_vs_spy,
                           :position_size_usd, :shares, :risk_amount,
                           :expected_return_pct, :expected_timeframe, :reasoning,
                           'pending')""",
                {"created_at": _now(), **data},
            )
            return cur.lastrowid

    def insert_mtf_conflict(self, data: dict[str, Any]) -> None:
        """Lane 4: log every thesis-TF conflict with raw inputs (2-week review)."""
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO mtf_conflicts (ts, symbol, strategy, direction, band,
                                              biases_json, label, note)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (_now(), data.get("symbol"), data.get("strategy"), data.get("direction"),
                 data.get("band"), json.dumps(data.get("biases") or {}),
                 data.get("label"), data.get("note")),
            )

    # ------------------------------------------------------- news/earnings cache
    def insert_news_items(self, items: list[dict[str, Any]]) -> int:
        """Append-only news store (Addendum 7); dedup on headline hash. Returns
        the number of NEW rows inserted."""
        if not items:
            return 0
        n = 0
        with self._conn() as conn:
            for it in items:
                h = it.get("hash")
                if not h:
                    continue
                cur = conn.execute(
                    """INSERT OR IGNORE INTO news_items
                       (hash, symbol, headline, source, url, published_ts, first_seen)
                       VALUES (?,?,?,?,?,?,?)""",
                    (h, (it.get("symbol") or None), it.get("headline"), it.get("source"),
                     it.get("url"), it.get("datetime"), _now()))
                n += cur.rowcount
        return n

    def get_news_items(self, since_ts: int, symbol: Optional[str] = None) -> list[dict[str, Any]]:
        """News published since a unix timestamp (for 24h clustering + 30d baseline)."""
        q = "SELECT hash, symbol, headline, source, url, published_ts FROM news_items WHERE published_ts >= ?"
        params: list[Any] = [since_ts]
        if symbol:
            q += " AND symbol = ?"; params.append(symbol.upper())
        with self._conn() as conn:
            return [{"hash": r["hash"], "symbol": r["symbol"], "headline": r["headline"],
                     "source": r["source"], "url": r["url"], "datetime": r["published_ts"]}
                    for r in conn.execute(q, params).fetchall()]

    def cache_get(self, key: str) -> Optional[dict[str, Any]]:
        """{'payload': .., 'fetched_at': iso, 'age_seconds': float} or None."""
        with self._conn() as conn:
            row = conn.execute("SELECT payload_json, fetched_at FROM news_cache WHERE key = ?",
                               (key,)).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, ValueError):
            return None
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(row["fetched_at"])).total_seconds()
        except (TypeError, ValueError):
            age = None
        return {"payload": payload, "fetched_at": row["fetched_at"], "age_seconds": age}

    def cache_put(self, key: str, payload: Any) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO news_cache (key, payload_json, fetched_at) VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET payload_json=excluded.payload_json,
                                                  fetched_at=excluded.fetched_at""",
                (key, json.dumps(payload), _now()),
            )

    def days_to_earnings(self, symbol: Optional[str]) -> Optional[int]:
        """Trading-agnostic calendar-day distance to the symbol's next earnings,
        from the cached Finnhub calendar ('earnings:calendar'). None if unknown."""
        if not symbol:
            return None
        hit = self.cache_get("earnings:calendar")
        if not hit:
            return None
        # earnings dates are US-market (ET) dates; UTC "today" is already
        # tomorrow during the ET evening, which would shave a day off
        try:
            from zoneinfo import ZoneInfo
            today = datetime.now(ZoneInfo("America/New_York")).date()
        except Exception:
            today = (datetime.now(timezone.utc) - timedelta(hours=4)).date()
        best: Optional[int] = None
        for e in (hit["payload"] or {}).get("earningsCalendar", []):
            if str(e.get("symbol", "")).upper() != str(symbol).upper():
                continue
            try:
                d = datetime.fromisoformat(e.get("date", "")).date()
            except (TypeError, ValueError):
                continue
            delta = (d - today).days
            if delta >= 0 and (best is None or delta < best):
                best = delta
        return best

    # ------------------------------------------------ Addendum 2: small-cap lane
    _SC_UNIVERSE_COLS = (
        "symbol", "updated_at", "price", "price_tier", "exchange", "sector_name",
        "float_shares", "float_est", "so_proxy", "float_tier", "avg_dollar_vol_20d",
        "rel_vol", "bb_percentile", "daily_compression", "compression_extreme",
        "squeeze_days", "up_wow", "consecutive_up_weeks", "dilution_risk",
        "upside_to_target_pct", "has_options", "options_liquid", "has_leaps", "signals_json",
    )

    def upsert_smallcap_universe(self, row: dict[str, Any]) -> None:
        """Upsert one screened+enriched small-cap. Booleans coerced to 0/1; only
        known columns are written. updated_at defaults to now if absent."""
        data = {k: (int(v) if isinstance(v, bool) else v)
                for k, v in row.items() if k in self._SC_UNIVERSE_COLS}
        data.setdefault("updated_at", _now())
        cols = list(data)
        placeholders = ",".join("?" for _ in cols)
        updates = ",".join(f"{c}=excluded.{c}" for c in cols if c != "symbol")
        with self._conn() as conn:
            conn.execute(
                f"INSERT INTO smallcap_universe ({','.join(cols)}) VALUES ({placeholders}) "
                f"ON CONFLICT(symbol) DO UPDATE SET {updates}",
                [data[c] for c in cols],
            )

    def get_smallcap_universe(self, *, max_age_hours: Optional[float] = 48,
                              tier: Optional[str] = None) -> list[dict[str, Any]]:
        """Fresh universe rows (default: refreshed within 48h), deathwatch already
        excluded at build time. signals_json is parsed into `signals`."""
        q = "SELECT * FROM smallcap_universe"
        clauses, params = [], []
        if max_age_hours is not None:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
            clauses.append("updated_at >= ?"); params.append(cutoff)
        if tier:
            clauses.append("float_tier = ?"); params.append(tier)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY rel_vol IS NULL, rel_vol DESC"
        with self._conn() as conn:
            rows = [dict(r) for r in conn.execute(q, params).fetchall()]
        for r in rows:
            try:
                r["signals"] = json.loads(r.get("signals_json") or "{}")
            except (TypeError, ValueError):
                r["signals"] = {}
        return rows

    def upsert_smallcap_deathwatch(self, symbol: str, reason: str, detail: str = "") -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO smallcap_deathwatch (symbol, reason, detail, added_at, last_checked)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(symbol) DO UPDATE SET reason=excluded.reason,
                       detail=excluded.detail, last_checked=excluded.last_checked""",
                (symbol.upper(), reason, detail, _now(), _now()),
            )

    def delete_smallcap_deathwatch(self, symbol: str) -> None:
        """Names exit deathwatch ONLY by aging out of the criteria (builder calls
        this when a re-check finds no hit) -- never a manual reprieve."""
        with self._conn() as conn:
            conn.execute("DELETE FROM smallcap_deathwatch WHERE symbol = ?", (symbol.upper(),))

    def is_on_deathwatch(self, symbol: str) -> bool:
        with self._conn() as conn:
            return conn.execute("SELECT 1 FROM smallcap_deathwatch WHERE symbol = ?",
                                (symbol.upper(),)).fetchone() is not None

    def get_smallcap_deathwatch(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM smallcap_deathwatch ORDER BY added_at DESC").fetchall()]

    def count_open_smallcap(self, lane: Optional[str] = None) -> int:
        """Open book='smallcap' trades, optionally one lane -- for the Hail-Mary
        cage (max 2 open)."""
        q = "SELECT COUNT(*) FROM paper_trades WHERE book = 'smallcap' AND status = 'open'"
        params: list[Any] = []
        if lane:
            q += " AND lane = ?"; params.append(lane)
        with self._conn() as conn:
            return int(conn.execute(q, params).fetchone()[0])

    def get_smallcap_trades(self, *, status: Optional[str] = None,
                            lane: Optional[str] = None) -> list[dict[str, Any]]:
        """book='smallcap' trades for the /smallcaps/record page (parsed trigger)."""
        q = "SELECT * FROM paper_trades WHERE book = 'smallcap'"
        params: list[Any] = []
        if status:
            q += " AND status = ?"; params.append(status)
        if lane:
            q += " AND lane = ?"; params.append(lane)
        q += " ORDER BY entry_date DESC"
        with self._conn() as conn:
            rows = [dict(r) for r in conn.execute(q, params).fetchall()]
        for r in rows:
            try:
                r["trigger"] = json.loads(r.get("trigger_json") or "{}")
            except (TypeError, ValueError):
                r["trigger"] = {}
        return rows

    def get_proposals(self, status: Optional[str] = None, account_type: Optional[str] = None) -> list[dict[str, Any]]:
        # proposals.direction is authoritative as of 2026-07-11 (Lane 1.4): written
        # at insert time for new rows, backfilled for all 284 older rows. No
        # paper_trades JOIN is needed to recover direction anymore.
        query = "SELECT * FROM proposals"
        clauses, params = [], []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if account_type:
            clauses.append("account_type = ?")
            params.append(account_type)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC"
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_proposal(self, proposal_id: int) -> Optional[dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
            return dict(row) if row else None

    def update_proposal_status(self, proposal_id: int, status: str, order_id: Optional[str] = None) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE proposals SET status = ?, order_id = ?, decided_at = ? WHERE id = ?",
                (status, order_id, _now(), proposal_id),
            )

    def expire_pending_proposals(self) -> int:
        """Mark still-pending proposals from prior scans as 'expired' so each
        scan presents a clean current snapshot (paper_trades keep the history)."""
        with self._conn() as conn:
            cur = conn.execute("UPDATE proposals SET status='expired' WHERE status='pending'")
            return cur.rowcount

    # ----------------------------------------------------- paper trades (sim)
    def open_paper_trade(self, data: dict[str, Any]) -> Optional[int]:
        """Open a simulated trade from a proposal. Skips if an OPEN trade for
        the same symbol+strategy already exists, so re-running a scan (same day
        or later) never piles up duplicate open trades."""
        data = {**data, "entry_date": data.get("entry_date", _now()),
                "direction": data.get("direction", "long")}
        # default any journal/grade fields the caller didn't supply so the
        # named-param INSERT never raises on a missing key.
        for k in ("book", "source", "archetype", "timeframe_band", "entry_type",
                  "pattern", "rs_vs_spy", "compression_tf", "planned_rr",
                  "process_grade", "process_score", "process_flags", "process_notes",
                  "shares", "position_value", "market_regime", "mtf_alignment",
                  "lane", "lane_score", "trigger_json",
                  "composite_score", "price_tier", "hold_band",
                  # proposal-only fields -- None for non-proposal callers (small-caps)
                  "proposal_id", "account_type", "confidence", "num_edges", "edges_fired"):
            data.setdefault(k, None)
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO paper_trades
                   (proposal_id, symbol, account_type, strategy, direction, confidence, num_edges,
                    edges_fired, sector_name, entry_price, stop_loss, target_price,
                    expected_timeframe, entry_date, max_hold_days, status,
                    book, source, archetype, timeframe_band, entry_type, pattern, rs_vs_spy,
                    compression_tf, planned_rr, process_grade, process_score, process_flags,
                    process_notes, shares, position_value, market_regime, mtf_alignment,
                    lane, lane_score, trigger_json, composite_score, price_tier, hold_band)
                   SELECT :proposal_id, :symbol, :account_type, :strategy, :direction, :confidence,
                          :num_edges, :edges_fired, :sector_name, :entry_price, :stop_loss,
                          :target_price, :expected_timeframe, :entry_date, :max_hold_days, 'open',
                          :book, :source, :archetype, :timeframe_band, :entry_type, :pattern,
                          :rs_vs_spy, :compression_tf, :planned_rr, :process_grade, :process_score,
                          :process_flags, :process_notes, :shares, :position_value,
                          :market_regime, :mtf_alignment, :lane, :lane_score, :trigger_json,
                          :composite_score, :price_tier, :hold_band
                   WHERE NOT EXISTS (
                       SELECT 1 FROM paper_trades
                       WHERE symbol = :symbol AND strategy = :strategy AND status = 'open'
                   )""",
                data,
            )
            return cur.lastrowid or None

    def get_paper_trades(self, status: Optional[str] = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM paper_trades"
        params: list[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY entry_date DESC"
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(query, params).fetchall()]

    # Lane 5: server-side sort allowlist. Values are SQL expressions (never user
    # input); rr/quality COALESCE to the proposal JOIN, grades map to ordinals.
    _ALGO_SORTS = {
        "entry_date": "pt.entry_date",
        "symbol": "pt.symbol",
        "setup": "pt.archetype",
        "band": "pt.timeframe_band",
        "rr": "COALESCE(pt.planned_rr, p.risk_reward)",
        "quality": "p.quality_score",
        "grade": ("CASE COALESCE(NULLIF(pt.process_grade,'UNGRADED'), pt.retro_grade) "
                  "WHEN 'A' THEN 5 WHEN 'B' THEN 4 WHEN 'C' THEN 3 WHEN 'D' THEN 2 "
                  "WHEN 'F' THEN 1 ELSE NULL END"),
        "r_multiple": "pt.r_multiple",
        "return_pct": "pt.return_pct",
        "mae_r": "pt.mae_r",
        "mfe_r": "pt.mfe_r",
        "hold_days": "julianday(COALESCE(pt.exit_date, datetime('now'))) - julianday(pt.entry_date)",
        "exit_reason": "pt.exit_reason",
    }
    # Lane 5 facet params -> columns (exact-match, multi-value OR within a group)
    _ALGO_FACETS = {
        "setup": "pt.archetype", "direction": "pt.direction", "band": "pt.timeframe_band",
        "outcome": "pt.outcome", "exit_reason": "pt.exit_reason", "quadrant": "pt.quadrant",
        "sector": "pt.sector_name", "market_regime": "pt.market_regime",
    }

    def get_algo_trades(self, status: Optional[str] = None,
                        sort: Optional[str] = None, direction: str = "desc",
                        facets: Optional[dict[str, list[str]]] = None) -> list[dict[str, Any]]:
        """Algo-book trades LEFT-JOINed to their originating proposal (via
        proposal_id), so the dashboard shows the same rich detail the proposal
        table already has -- R:R, quality, edges, written rationale -- even for
        legacy rows that predate the paper-trade grade/rr columns.

        Lane 5 (all additive; defaults preserve the original behavior): `sort`
        from the _ALGO_SORTS allowlist (nulls always last), `direction`
        asc|desc, `facets` {group: [values]} AND-ed across groups, OR within.
        """
        query = """
            SELECT pt.*,
                   p.risk_reward   AS proposal_risk_reward,
                   p.quality_score AS proposal_quality_score,
                   p.edges_fired   AS proposal_edges_fired,
                   p.num_edges     AS proposal_num_edges,
                   p.reasoning     AS proposal_reasoning
            FROM paper_trades pt
            LEFT JOIN proposals p ON pt.proposal_id = p.id
            WHERE (pt.book IS NULL OR pt.book != 'smallcap')
        """
        params: list[Any] = []
        if status:
            query += " AND pt.status = ?"
            params.append(status)
        if facets:
            with self._conn() as conn:
                existing = {r["name"] for r in conn.execute("PRAGMA table_info(paper_trades)")}
        for group, values in (facets or {}).items():
            col = self._ALGO_FACETS.get(group)
            vals = [v for v in (values or []) if v]
            # facet columns that don't exist yet (e.g. market_regime until Lane 4
            # lands) are silently skipped rather than crashing the query
            if col and vals and col.split(".")[-1] in existing:
                query += f" AND {col} IN ({','.join('?' * len(vals))})"
                params.extend(vals)
        expr = self._ALGO_SORTS.get(sort or "")
        if expr:
            d = "ASC" if str(direction).lower() == "asc" else "DESC"
            query += f" ORDER BY ({expr}) IS NULL, ({expr}) {d}, pt.entry_date DESC"
        else:
            query += " ORDER BY pt.entry_date DESC"
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(query, params).fetchall()]

    _ENRICHABLE = frozenset({"exit_reason", "mae_r", "mfe_r", "quadrant",
                             "retro_grade", "retro_score"})

    def enrich_paper_trade(self, trade_id: int, **fields: Any) -> None:
        """Enrich-only writer for derived post-close fields: each column is set
        ONLY if currently NULL (ground rule: never overwrite a populated field).
        Column names are restricted to a fixed allowlist."""
        with self._conn() as conn:
            for col, val in fields.items():
                if col not in self._ENRICHABLE:
                    raise ValueError(f"enrich_paper_trade: column '{col}' not allowed")
                conn.execute(
                    f"UPDATE paper_trades SET {col} = ? WHERE id = ? AND {col} IS NULL",
                    (val, trade_id),
                )

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

    def get_track_record(self) -> list[dict[str, Any]]:
        """Win rate / avg return grouped by confidence tier and strategy,
        over all CLOSED paper trades."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT strategy, confidence,
                          COUNT(*) AS n,
                          SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) AS wins,
                          ROUND(AVG(return_pct), 2) AS avg_return,
                          ROUND(AVG(CASE WHEN outcome = 'win' THEN return_pct END), 2) AS avg_win,
                          ROUND(AVG(CASE WHEN outcome = 'loss' THEN return_pct END), 2) AS avg_loss
                   FROM paper_trades
                   WHERE status = 'closed'
                   GROUP BY strategy, confidence
                   ORDER BY strategy, confidence DESC""").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["win_rate"] = round(100 * d["wins"] / d["n"], 1) if d["n"] else 0.0
            result.append(d)
        return result

    def get_edge_performance(self) -> list[dict[str, Any]]:
        """For each edge, how often trades that fired it ended up winning.
        The core of the feedback loop -- which edges actually predict wins."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT edges_fired, outcome, return_pct FROM paper_trades WHERE status = 'closed'"
            ).fetchall()
        stats: dict[str, dict[str, float]] = {}
        for r in rows:
            for edge in (r["edges_fired"] or "").split(", "):
                edge = edge.strip()
                if not edge:
                    continue
                s = stats.setdefault(edge, {"n": 0, "wins": 0, "ret": 0.0})
                s["n"] += 1
                s["wins"] += 1 if r["outcome"] == "win" else 0
                s["ret"] += r["return_pct"] or 0.0
        out = []
        for edge, s in stats.items():
            out.append({
                "edge": edge, "n": int(s["n"]),
                "win_rate": round(100 * s["wins"] / s["n"], 1) if s["n"] else 0.0,
                "avg_return": round(s["ret"] / s["n"], 2) if s["n"] else 0.0,
            })
        out.sort(key=lambda x: (x["win_rate"], x["n"]), reverse=True)
        return out

    # -------------------------------------------------------- catalyst watchlist
    def add_watchlist(self, symbol: str, note: str = "") -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO watchlist (symbol, note, added_at) VALUES (?, ?, ?)
                   ON CONFLICT(symbol) DO UPDATE SET note=excluded.note""",
                (symbol.upper().strip(), note, _now()),
            )

    def remove_watchlist(self, symbol: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol.upper().strip(),))

    def get_watchlist(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM watchlist ORDER BY added_at DESC").fetchall()]

    # ----------------------------------------------------------------- trades
    def insert_trade(self, data: dict[str, Any]) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO trades
                   (proposal_id, account_type, symbol, side, quantity, entry_price,
                    exit_price, entry_time, exit_time, pnl, pnl_pct, status, order_id)
                   VALUES (:proposal_id, :account_type, :symbol, :side, :quantity,
                           :entry_price, :exit_price, :entry_time, :exit_time, :pnl,
                           :pnl_pct, :status, :order_id)""",
                data,
            )
            return cur.lastrowid

    def get_trades(self, account_type: Optional[str] = None, status: Optional[str] = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM trades"
        clauses, params = [], []
        if account_type:
            clauses.append("account_type = ?")
            params.append(account_type)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY entry_time DESC"
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def close_trade(self, trade_id: int, exit_price: float, pnl: float, pnl_pct: float) -> None:
        with self._conn() as conn:
            conn.execute(
                """UPDATE trades SET exit_price = ?, exit_time = ?, pnl = ?,
                   pnl_pct = ?, status = 'closed' WHERE id = ?""",
                (exit_price, _now(), pnl, pnl_pct, trade_id),
            )

    # -------------------------------------------------------------- positions
    def upsert_position(self, data: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO positions
                   (account_type, symbol, quantity, avg_price, current_price,
                    market_value, unrealized_pnl, unrealized_pnl_pct, updated_at)
                   VALUES (:account_type, :symbol, :quantity, :avg_price, :current_price,
                           :market_value, :unrealized_pnl, :unrealized_pnl_pct, :updated_at)
                   ON CONFLICT(account_type, symbol) DO UPDATE SET
                     quantity=excluded.quantity, avg_price=excluded.avg_price,
                     current_price=excluded.current_price, market_value=excluded.market_value,
                     unrealized_pnl=excluded.unrealized_pnl,
                     unrealized_pnl_pct=excluded.unrealized_pnl_pct,
                     updated_at=excluded.updated_at""",
                {"updated_at": _now(), **data},
            )

    def get_positions(self, account_type: Optional[str] = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM positions"
        params: list[Any] = []
        if account_type:
            query += " WHERE account_type = ?"
            params.append(account_type)
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def remove_position(self, account_type: str, symbol: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM positions WHERE account_type = ? AND symbol = ?",
                (account_type, symbol),
            )

    # ------------------------------------------------------------ performance
    def insert_performance_snapshot(self, data: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO performance_snapshots
                   (account_type, date, total_value, cash, daily_pnl, daily_pnl_pct,
                    total_pnl, total_pnl_pct, win_rate, num_trades, num_wins, num_losses)
                   VALUES (:account_type, :date, :total_value, :cash, :daily_pnl,
                           :daily_pnl_pct, :total_pnl, :total_pnl_pct, :win_rate,
                           :num_trades, :num_wins, :num_losses)
                   ON CONFLICT(account_type, date) DO UPDATE SET
                     total_value=excluded.total_value, cash=excluded.cash,
                     daily_pnl=excluded.daily_pnl, daily_pnl_pct=excluded.daily_pnl_pct,
                     total_pnl=excluded.total_pnl, total_pnl_pct=excluded.total_pnl_pct,
                     win_rate=excluded.win_rate, num_trades=excluded.num_trades,
                     num_wins=excluded.num_wins, num_losses=excluded.num_losses""",
                data,
            )

    def get_performance(self, account_type: Optional[str] = None, limit: int = 90) -> list[dict[str, Any]]:
        query = "SELECT * FROM performance_snapshots"
        params: list[Any] = []
        if account_type:
            query += " WHERE account_type = ?"
            params.append(account_type)
        query += " ORDER BY date DESC LIMIT ?"
        params.append(limit)
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    # ============================================================ B3 risk state
    def get_risk_state(self, account_type: str) -> Optional[dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM risk_state WHERE account_type = ?",
                               (account_type,)).fetchone()
            return dict(row) if row else None

    def upsert_risk_state(self, account_type: str, **fields: Any) -> None:
        """Additive upsert -- pass only the columns that changed."""
        allowed = {"equity_high_water_mark", "day_key", "day_start_equity",
                   "realized_pnl_today", "halted", "halt_reason", "halted_at"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        sets["updated_at"] = _now()
        cols = ", ".join(sets)
        placeholders = ", ".join(f":{k}" for k in sets)
        updates = ", ".join(f"{k}=excluded.{k}" for k in sets)
        params = dict(sets, account_type=account_type)
        with self._conn() as conn:
            conn.execute(
                f"""INSERT INTO risk_state (account_type, {cols})
                    VALUES (:account_type, {placeholders})
                    ON CONFLICT(account_type) DO UPDATE SET {updates}""", params)

    # -------------------------------------------- open REAL exposure aggregations
    # These count only rows that represent live-or-working REAL Alpaca exposure
    # (is_real=1, status='open', not rejected). A row is inserted at SUBMISSION
    # time (before fill), so successive gate evaluations in one scan see prior
    # submissions and cannot blow through the caps before fills settle.
    _OPEN_REAL = ("account_type = ? AND is_real = 1 AND status = 'open' "
                  "AND COALESCE(was_rejected, 0) = 0")

    def sum_open_risk(self, account_type: str = "algo") -> float:
        """Sum of |entry-stop| * shares over open+working real positions."""
        with self._conn() as conn:
            row = conn.execute(
                f"""SELECT COALESCE(SUM(ABS(entry_price - stop_loss)
                        * COALESCE(filled_qty, shares, 0)), 0)
                    FROM paper_trades WHERE {self._OPEN_REAL}""",
                (account_type,)).fetchone()
            return float(row[0] or 0.0)

    def count_open_by_sector(self, account_type: str = "algo") -> dict[str, int]:
        with self._conn() as conn:
            rows = conn.execute(
                f"""SELECT COALESCE(sector_name, 'Unknown') AS s, COUNT(*) AS n
                    FROM paper_trades WHERE {self._OPEN_REAL} GROUP BY s""",
                (account_type,)).fetchall()
            return {r["s"]: int(r["n"]) for r in rows}

    def open_notional_by_lane(self, account_type: str = "algo") -> dict[str, float]:
        with self._conn() as conn:
            rows = conn.execute(
                f"""SELECT COALESCE(lane, 'none') AS l,
                           COALESCE(SUM(COALESCE(filled_qty, shares, 0) * entry_price), 0) AS notional
                    FROM paper_trades WHERE {self._OPEN_REAL} GROUP BY l""",
                (account_type,)).fetchall()
            return {r["l"]: float(r["notional"]) for r in rows}

    # -------------------------------------------------------------- B1 fills log
    def insert_algo_trade(self, trade: dict[str, Any]) -> int:
        """Insert a book='algo' paper_trades row for a REAL Alpaca paper order at
        SUBMISSION time (before fill). Returns the new trade id. entry_price /
        stop_loss / target_price / symbol / entry_date must be present (NOT NULL)."""
        cols = ("proposal_id", "symbol", "account_type", "strategy", "direction",
                "sector_name", "entry_price", "stop_loss", "target_price",
                "expected_timeframe", "entry_date", "max_hold_days", "status", "book",
                "source", "lane", "lane_score", "composite_score", "price_tier",
                "hold_band", "shares", "position_value", "trigger_json",
                "broker_order_id", "client_order_id", "order_status", "submitted_at",
                "is_real", "filled_qty", "fill_price", "slippage_bps", "was_rejected",
                "partial_fill", "time_to_fill")
        data = {c: trade.get(c) for c in cols}
        data["status"] = data.get("status") or "open"
        data["book"] = data.get("book") or "algo"
        data["is_real"] = 1 if data.get("is_real") in (1, True) else data.get("is_real")
        data["entry_date"] = data.get("entry_date") or _now()
        collist = ", ".join(cols)
        placeholders = ", ".join(f":{c}" for c in cols)
        with self._conn() as conn:
            cur = conn.execute(
                f"INSERT INTO paper_trades ({collist}) VALUES ({placeholders})", data)
            return int(cur.lastrowid)

    def record_open_fill(self, trade_id: int, **fill: Any) -> None:
        allowed = {"broker_order_id", "client_order_id", "order_status", "submitted_at",
                   "fill_price", "filled_qty", "slippage_bps", "was_rejected",
                   "partial_fill", "time_to_fill", "is_real"}
        sets = {k: v for k, v in fill.items() if k in allowed}
        if not sets:
            return
        assignments = ", ".join(f"{k} = :{k}" for k in sets)
        with self._conn() as conn:
            conn.execute(f"UPDATE paper_trades SET {assignments} WHERE id = :tid",
                         dict(sets, tid=trade_id))

    def record_exit_fill(self, trade_id: int, **fill: Any) -> None:
        allowed = {"exit_fill_price", "exit_slippage_bps", "exit_time_to_fill",
                   "gap_through_stop", "real_pnl_usd", "real_return_pct",
                   "real_r_multiple", "order_status"}
        sets = {k: v for k, v in fill.items() if k in allowed}
        if not sets:
            return
        assignments = ", ".join(f"{k} = :{k}" for k in sets)
        with self._conn() as conn:
            conn.execute(f"UPDATE paper_trades SET {assignments} WHERE id = :tid",
                         dict(sets, tid=trade_id))

    def insert_order_fill(self, *, trade_id: Optional[int], broker_order_id: Optional[str],
                          leg: str, event_type: str, qty: Optional[float] = None,
                          price: Optional[float] = None, raw_json: Optional[str] = None) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO order_fills (trade_id, broker_order_id, leg, event_type,
                        qty, price, ts, raw_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (trade_id, broker_order_id, leg, event_type, qty, price, _now(), raw_json))

    def find_algo_trade_by_client_order_id(self, client_order_id: str) -> Optional[dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM paper_trades WHERE client_order_id = ?",
                               (client_order_id,)).fetchone()
            return dict(row) if row else None

    def get_open_algo_trades(self, account_type: str = "algo") -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM paper_trades WHERE {self._OPEN_REAL}", (account_type,)).fetchall()
            return [dict(r) for r in rows]

    def get_sim_vs_real(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM sim_vs_real LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]
