"""
CLI entry point for the autonomous trading system.

Commands:
  init-db   Create/verify the SQLite schema and seed account rows.
  scan      Run one full analysis pass (regime -> sectors -> screen ->
            technical analysis -> proposals). Read-only; never trades.
  autoscan  Run `scan` repeatedly on a timer (still never trades -- use
            the dashboard's Approve button, or the API, to execute).
  serve     Start the FastAPI dashboard/API server.
"""

from __future__ import annotations

import argparse
import logging
import time

from src.api_server import CONFIG, DB, RH, run_full_scan

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def cmd_init_db(_args: argparse.Namespace) -> None:
    # Database() already created the schema and seeded accounts on import
    # of src.api_server; this just confirms it for the user.
    accounts = [dict(DB.get_account(a)) for a in CONFIG["accounts"] if DB.get_account(a)]
    print(f"Database ready at {CONFIG['database']['path']}")
    for a in accounts:
        print(f"  account={a['account_type']} balance=${a['current_balance']}")


def cmd_scan(_args: argparse.Namespace) -> None:
    summary = run_full_scan(CONFIG, DB, RH)
    print(f"Regime: {summary['market_regime']['regime']} ({summary['market_regime']['symbol']} "
          f"${summary['market_regime']['price']})")
    print(f"Hot sectors: {', '.join(summary['hot_sectors'])}")
    for account_type, count in summary["proposals"].items():
        print(f"  {account_type}: {count} new proposal(s)")
    print("Review proposals in the dashboard (or GET /api/proposals) and approve manually.")


def cmd_autoscan(args: argparse.Namespace) -> None:
    interval_seconds = max(60, args.interval * 60)
    print(f"Autoscan started: running every {args.interval} minute(s). Ctrl+C to stop.")
    try:
        while True:
            cmd_scan(args)
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("Autoscan stopped.")


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn
    from src.api_server import app

    host = args.host or CONFIG["api"]["host"]
    port = args.port or CONFIG["api"]["port"]
    uvicorn.run(app, host=host, port=port)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trading-system")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="Create/verify the database schema").set_defaults(func=cmd_init_db)

    sub.add_parser("scan", help="Run one full analysis pass").set_defaults(func=cmd_scan)

    autoscan = sub.add_parser("autoscan", help="Run scan repeatedly on a timer")
    autoscan.add_argument("--interval", type=int, default=15, help="Minutes between scans (default 15)")
    autoscan.set_defaults(func=cmd_autoscan)

    serve = sub.add_parser("serve", help="Start the FastAPI dashboard/API server")
    serve.add_argument("--host", type=str, default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.set_defaults(func=cmd_serve)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
