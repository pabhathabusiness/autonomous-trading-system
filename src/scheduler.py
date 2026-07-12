"""
Autonomous scheduler -- the engine that makes the system run itself.

Runs as a daemon thread inside the always-on service. It replaces the manual
"Run Scan" button entirely:

  * MONITOR (every monitor_interval_sec, always): marks every open paper trade
    against Alpaca's live feed and closes any that have hit their stop/target,
    then runs the daily-replay resolver as a backstop. This is what closes the
    trades that were previously stuck open (e.g. RPD hitting its target, KTOS
    falling through its stop) -- and it runs on boot too, so already-open
    positions get resolved immediately, not just future ones.

  * SCAN (every scan_interval_min, market hours only): runs a full scan to open
    new qualifying trades across the bands.

Execution safety: opening trades is SIMULATED by default. Real Alpaca *paper*
bracket orders are only placed when config.autonomous.auto_execute is true, and
even then every order passes the execution_guard wall (paper account, paper
book only). auto_execute ships FALSE -- the bot is dormant until deliberately
enabled.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, time as dt_time, timezone

from src import paper_trader, post_close

logger = logging.getLogger(__name__)


def _now_et():
    """Current time in US/Eastern, with a safe fallback if tzdata is missing
    (Windows dev boxes) -- approximates ET as UTC-4 so market-hours gating still
    works well enough for the sim. The droplet (Ubuntu) has real tzdata."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        from datetime import timedelta
        return datetime.now(timezone.utc) - timedelta(hours=4)


def market_is_open(now=None) -> bool:
    now = now or _now_et()
    if now.weekday() >= 5:                       # Sat/Sun
        return False
    return dt_time(9, 30) <= now.time() <= dt_time(16, 0)


def close_on_live_cross(db, alpaca) -> int:
    """Close any open paper trade whose live price has crossed its frozen
    stop/target. Intraday-granular (Alpaca live), the fast path that catches a
    day-trade hitting its level between daily bars. Closes at the PLAN level
    (stop/target), consistent with the replay resolver. Returns #closed."""
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


class AutonomousScheduler:
    def __init__(self, config, db, alpaca, scan_fn):
        ac = config.get("autonomous", {}) or {}
        self.config = config
        self.db = db
        self.alpaca = alpaca
        self.scan_fn = scan_fn                    # zero-arg callable -> run_full_scan
        self.enabled = ac.get("enabled", True)
        self.scan_interval = max(60, ac.get("scan_interval_min", 15) * 60)
        self.monitor_interval = max(15, ac.get("monitor_interval_sec", 60))
        self.market_hours_only = ac.get("market_hours_only", True)
        self.auto_execute = ac.get("auto_execute", False)
        self._stop = threading.Event()
        self._lock = threading.Lock()             # serialize our own scan/monitor
        self._thread = None
        self._last_scan = 0.0
        self.last_monitor_at = None
        self.last_scan_at = None

    # ------------------------------------------------------------------ control
    def start(self) -> None:
        if not self.enabled:
            logger.info("Autonomous scheduler DISABLED (autonomous.enabled=false)")
            return
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="autoscheduler", daemon=True)
        self._thread.start()
        logger.info("Autonomous scheduler STARTED (scan/%ss monitor/%ss market_hours_only=%s auto_execute=%s)",
                    self.scan_interval, self.monitor_interval, self.market_hours_only, self.auto_execute)

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> dict:
        return {
            "enabled": self.enabled,
            "running": bool(self._thread and self._thread.is_alive()),
            "auto_execute": self.auto_execute,
            "market_open": market_is_open(),
            "scan_interval_sec": self.scan_interval,
            "monitor_interval_sec": self.monitor_interval,
            "last_monitor_at": self.last_monitor_at,
            "last_scan_at": self.last_scan_at,
        }

    # --------------------------------------------------------------------- loop
    def _run(self) -> None:
        # Resolve immediately on boot so ALREADY-open trades that hit their
        # levels (the stuck RPD / KTOS case) get closed right away.
        self._safe(self._monitor, "startup-monitor")
        while not self._stop.wait(self.monitor_interval):
            self._safe(self._monitor, "monitor")
            due = time.time() - self._last_scan >= self.scan_interval
            if due and (market_is_open() if self.market_hours_only else True):
                self._safe(self._scan, "scan")
                self._last_scan = time.time()

    def _monitor(self) -> None:
        with self._lock:
            live_closed = close_on_live_cross(self.db, self.alpaca)
            summary = paper_trader.resolve_open(self.db)
            # derive exit_reason / MAE-MFE / quadrant for anything newly closed
            # (enrich-only writes; the close functions themselves stay untouched)
            self._safe(lambda: post_close.enrich_closed(self.db), "post-close-enrich")
        self.last_monitor_at = datetime.now(timezone.utc).isoformat()
        if live_closed or summary.get("wins") or summary.get("losses") or summary.get("expired"):
            logger.info("Monitor: live_closed=%s replay=%s", live_closed, summary)

    def _scan(self) -> None:
        with self._lock:
            result = self.scan_fn()
        self.last_scan_at = datetime.now(timezone.utc).isoformat()
        logger.info("Autonomous scan done: proposals=%s", (result or {}).get("proposals"))

    @staticmethod
    def _safe(fn, label: str) -> None:
        try:
            fn()
        except Exception:
            logger.exception("Autonomous scheduler %s failed", label)
