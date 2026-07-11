"""
SQLite persistence layer for the autonomous trading system.

Every other module reads/writes through the Database class rather than
touching sqlite3 directly, so the schema lives in exactly one place.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
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
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO proposals
                   (created_at, account_type, symbol, sector_name, entry_price,
                    stop_loss, target_price, risk_reward, quality_score,
                    confidence, num_edges, edges_fired, strategy,
                    position_size_usd, shares, risk_amount, expected_return_pct,
                    expected_timeframe, reasoning, status)
                   VALUES (:created_at, :account_type, :symbol, :sector_name,
                           :entry_price, :stop_loss, :target_price, :risk_reward,
                           :quality_score, :confidence, :num_edges, :edges_fired,
                           :strategy, :position_size_usd, :shares, :risk_amount,
                           :expected_return_pct, :expected_timeframe, :reasoning,
                           'pending')""",
                {"created_at": _now(), **data},
            )
            return cur.lastrowid

    def get_proposals(self, status: Optional[str] = None, account_type: Optional[str] = None) -> list[dict[str, Any]]:
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
                  "shares", "position_value"):
            data.setdefault(k, None)
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO paper_trades
                   (proposal_id, symbol, account_type, strategy, direction, confidence, num_edges,
                    edges_fired, sector_name, entry_price, stop_loss, target_price,
                    expected_timeframe, entry_date, max_hold_days, status,
                    book, source, archetype, timeframe_band, entry_type, pattern, rs_vs_spy,
                    compression_tf, planned_rr, process_grade, process_score, process_flags,
                    process_notes, shares, position_value)
                   SELECT :proposal_id, :symbol, :account_type, :strategy, :direction, :confidence,
                          :num_edges, :edges_fired, :sector_name, :entry_price, :stop_loss,
                          :target_price, :expected_timeframe, :entry_date, :max_hold_days, 'open',
                          :book, :source, :archetype, :timeframe_band, :entry_type, :pattern,
                          :rs_vs_spy, :compression_tf, :planned_rr, :process_grade, :process_score,
                          :process_flags, :process_notes, :shares, :position_value
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
