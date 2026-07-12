"""
FastAPI web API + dashboard for the autonomous trading system.

Owns config loading and full-scan orchestration so `main.py` (CLI) and
uvicorn (web server) share one code path. The scan pipeline only ever
writes 'pending' proposals -- the only route that can move money is
POST /api/proposals/{id}/approve, which represents a human clicking
"Approve" in the dashboard.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src import bias_strip as bias_strip_module
from src import drilldown as drilldown_module
from src import live as live_module
from src import market_overview as market_overview_module
from src import mtf_bias
from src import news_refresher
from src.finnhub_client import FinnhubClient
from src import paper_trader
from src.scheduler import AutonomousScheduler
from src.alpaca_client import AlpacaClient
from src.database import Database
from src.market_analyzer import MarketAnalyzer
from src.proposal_generator import ProposalGenerator
from src.risk_manager import RiskManager
from src.robinhood_client import RobinhoodClient
from src.screener import Screener
from src.sector_analyzer import SectorAnalyzer
from src.technical_analyzer import TIER_RANK, TechnicalAnalyzer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "config.json"
STATIC_DIR = Path(__file__).resolve().parent / "static"


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    if not path.exists():
        example = path.parent / "config.example.json"
        raise FileNotFoundError(
            f"{path} not found. Copy {example} to {path} and edit as needed."
        )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------- scan
def run_full_scan(config: dict[str, Any], db: Database, rh_client: RobinhoodClient) -> dict[str, Any]:
    """One full pass: market regime -> sector ranks -> per-account
    screen -> technical analysis -> proposals. Read-only / analysis-only;
    never places an order."""
    market = MarketAnalyzer(config).analyze_and_store(db)
    # Lane 4: keep the market-bias panel/regime fresh (TTL ~12h inside)
    try:
        mtf_bias.refresh_panel(db)
    except Exception:
        logger.exception("bias panel refresh failed")

    # each scan is a clean snapshot -- retire last scan's untouched proposals
    db.expire_pending_proposals()

    sector_analyzer = SectorAnalyzer(config)
    rankings, hot_sectors = sector_analyzer.analyze_and_store(db)

    proposal_generator = ProposalGenerator(config)
    summary: dict[str, Any] = {"market_regime": market, "hot_sectors": hot_sectors, "proposals": {}}

    for account_type in config["accounts"]:
        account_cfg = config["accounts"][account_type]
        # The 'algo' book (Log B) is not a screening account -- it mirrors every
        # generated proposal into its own $100k book (wired in step 3), so skip
        # it here. Also skip anything missing the screening config it needs.
        if account_cfg.get("book") == "algo" or "price_range" not in account_cfg:
            continue
        account = db.get_account(account_type)
        # When hide_balance is set, always size trades against the fixed
        # starting_balance rather than the (hidden) running balance -- the
        # account is treated as "always at that amount" for sizing.
        if account_cfg.get("hide_balance"):
            balance = account_cfg["starting_balance"]
        else:
            balance = account["current_balance"] if account else account_cfg["starting_balance"]

        screener = Screener(config, account_type)
        candidates = screener.run(hot_sectors, sector_analyzer)
        if candidates:
            db.insert_screened_stocks(candidates)

        proposals = proposal_generator.generate(account_type, candidates, market, balance)
        for p in proposals:
            analysis = p.pop("_analysis")
            db.insert_technical_analysis({**analysis, "symbol": p["symbol"]})
            mtf_bias.apply_to_proposal(db, p, analysis)   # Lane 4 stamp + penalty + conflict log
            pid = db.insert_proposal(p)
            # Autonomous Algo book (Log B), graded at open
            paper_trader.open_from_proposal(db, p, pid, analysis={**analysis, "symbol": p["symbol"]},
                                            config=config)

        summary["proposals"][account_type] = len(proposals)

    # Short-term momentum ideas across ALL hot sectors (5-10% in 1-3 days).
    summary["proposals"]["short_term"] = generate_short_term_ideas(
        config, db, hot_sectors, sector_analyzer, market)

    # Downside/short ideas for negative (downtrending) sectors.
    summary["proposals"]["downside"] = generate_downside_ideas(
        config, db, rankings, sector_analyzer)

    # Coiling / pre-breakout scan across hot + laggard-turning sectors + watchlist.
    turning = sector_analyzer.turning_sectors(rankings)
    summary["turning_sectors"] = turning
    summary["proposals"]["coiling"] = generate_coiling_ideas(
        config, db, hot_sectors, turning, sector_analyzer)

    # Feedback loop: resolve any open simulated trades against real prices.
    summary["paper_trades"] = paper_trader.resolve_open(db)

    logger.info("Scan complete: %s", summary)
    return summary


def generate_short_term_ideas(
    config: dict[str, Any], db: Database, hot_sectors: list[str],
    sector_analyzer: SectorAnalyzer, market: dict[str, Any],
) -> int:
    """Scan every hot sector's names for quick momentum setups and store the
    top N as `short_term` proposals. Deliberately lenient so the main page
    always has a spread of ideas across sectors."""
    st_cfg = config.get("technical", {}).get("short_term", {})
    count = st_cfg.get("main_count", 10)
    max_price = st_cfg.get("main_max_price", 100)
    min_edges = st_cfg.get("main_min_edges", 2)
    min_rr = st_cfg.get("main_min_risk_reward", 1.5)  # quality gate (was 1.2)

    # symbol -> sector (first sector wins), deduped across hot sectors
    symbol_sector: dict[str, str] = {}
    for sector in hot_sectors:
        for sym in sector_analyzer.candidates_for_sector(sector):
            symbol_sector.setdefault(sym, sector)

    scored: list[dict[str, Any]] = []
    for symbol, sector in symbol_sector.items():
        a = TECH.analyze_short_term(symbol)
        if not a or a["entry_price"] > max_price:
            continue
        if a["num_edges"] < min_edges or a["risk_reward"] < min_rr:
            continue
        a["sector_name"] = sector
        scored.append(a)

    scored.sort(key=lambda a: (a["quality_score"], a["num_edges"], a["risk_reward"]), reverse=True)
    top = scored[:count]

    risk_manager = RiskManager(config)
    agentic_max = config["accounts"]["agentic"]["price_range"][1]
    stored = 0
    for a in top:
        # cheap names -> aggressive bot, else the personal account
        account_type = "agentic" if a["entry_price"] <= agentic_max else "personal"
        acct_cfg = config["accounts"][account_type]
        if acct_cfg.get("hide_balance"):
            balance = acct_cfg["starting_balance"]
        else:
            acct = db.get_account(account_type)
            balance = acct["current_balance"] if acct else acct_cfg["starting_balance"]
        sizing = risk_manager.calculate_position_size(
            account_type=account_type, entry_price=a["entry_price"], stop_loss=a["stop_loss"],
            quality_score=a["quality_score"], account_balance=balance)
        if sizing is None:
            continue
        proposal = {
            "account_type": account_type, "symbol": a["symbol"], "sector_name": a["sector_name"],
            "entry_price": a["entry_price"], "stop_loss": a["stop_loss"], "target_price": a["target_price"],
            "risk_reward": a["risk_reward"], "quality_score": a["quality_score"],
            "confidence": a["confidence"], "num_edges": a["num_edges"], "edges_fired": a["edges_fired"],
            "strategy": "short_term",
            "position_size_usd": sizing["position_size_usd"], "shares": sizing["shares"],
            "risk_amount": sizing["risk_amount"], "expected_return_pct": a["expected_return_pct"],
            "expected_timeframe": a["expected_timeframe"],
            "reasoning": (f"{a['symbol']} ({a['sector_name']}) SHORT-TERM {a['confidence']} "
                          f"({a['num_edges']} edges): {a['edges_fired']}. Entry {a['entry_price']} / "
                          f"stop {a['stop_loss']} / target {a['target_price']} = {a['risk_reward']}:1, "
                          f"~{a['expected_return_pct']}% in {a['expected_timeframe']}."),
        }
        mtf_bias.apply_to_proposal(db, proposal, a)   # Lane 4 stamp + penalty + conflict log
        pid = db.insert_proposal(proposal)
        paper_trader.open_from_proposal(db, proposal, pid, analysis=a, config=config)
        stored += 1
    logger.info("Short-term ideas: %d stored (scanned %d names)", stored, len(symbol_sector))
    return stored


def generate_downside_ideas(
    config: dict[str, Any], db: Database, rankings: list[dict[str, Any]],
    sector_analyzer: SectorAnalyzer,
) -> int:
    """Scan NEGATIVE (downtrending) sectors for bearish/short setups and store
    them as `downside` proposals (direction=short) -- the opposite of the
    long playbook, for sectors where the trade is to the downside."""
    ds_cfg = config.get("technical", {}).get("downside", {})
    if not ds_cfg.get("enabled", True):
        return 0
    threshold = ds_cfg.get("sector_threshold", 0.0)
    count = ds_cfg.get("count", 8)
    min_edges = ds_cfg.get("min_edges", 5)
    min_rr = ds_cfg.get("min_risk_reward", 1.5)  # quality gate (was 1.3)
    max_price = ds_cfg.get("max_price", 200)
    max_sectors = ds_cfg.get("max_sectors", 5)

    # only the MOST-negative sectors (cheapest to scan, best short candidates)
    neg_ranked = sorted(
        [r for r in rankings if (r.get("composite_score") or 0) < threshold],
        key=lambda r: r.get("composite_score") or 0)
    negative = [r["sector_name"] for r in neg_ranked[:max_sectors]]
    symbol_sector: dict[str, str] = {}
    for sector in negative:
        for sym in sector_analyzer.candidates_for_sector(sector):
            symbol_sector.setdefault(sym, sector)

    scored: list[dict[str, Any]] = []
    for symbol, sector in symbol_sector.items():
        a = TECH.analyze_downside(symbol)
        if not a or a["entry_price"] > max_price:
            continue
        if a["num_edges"] < min_edges or a["risk_reward"] < min_rr:
            continue
        a["sector_name"] = sector
        scored.append(a)
    scored.sort(key=lambda a: (a["num_edges"], a["quality_score"], a["risk_reward"]), reverse=True)
    top = scored[:count]

    risk_manager = RiskManager(config)
    agentic_max = config["accounts"]["agentic"]["price_range"][1]
    stored = 0
    for a in top:
        account_type = "agentic" if a["entry_price"] <= agentic_max else "personal"
        acct_cfg = config["accounts"][account_type]
        if acct_cfg.get("hide_balance"):
            balance = acct_cfg["starting_balance"]
        else:
            acct = db.get_account(account_type)
            balance = acct["current_balance"] if acct else acct_cfg["starting_balance"]
        sizing = risk_manager.calculate_position_size(
            account_type=account_type, entry_price=a["entry_price"], stop_loss=a["stop_loss"],
            quality_score=a["quality_score"], account_balance=balance)
        if sizing is None:
            continue
        proposal = {
            "account_type": account_type, "symbol": a["symbol"], "sector_name": a["sector_name"],
            "entry_price": a["entry_price"], "stop_loss": a["stop_loss"], "target_price": a["target_price"],
            "risk_reward": a["risk_reward"], "quality_score": a["quality_score"],
            "confidence": a["confidence"], "num_edges": a["num_edges"], "edges_fired": a["edges_fired"],
            "strategy": "downside", "direction": "short",
            "position_size_usd": sizing["position_size_usd"], "shares": sizing["shares"],
            "risk_amount": sizing["risk_amount"], "expected_return_pct": a["expected_return_pct"],
            "expected_timeframe": a["expected_timeframe"],
            "reasoning": (f"SHORT {a['symbol']} ({a['sector_name']}) -- {a['confidence']} downside "
                          f"({a['num_edges']} edges): {a['edges_fired']}. Structure {a['daily_bias']} "
                          f"daily / {a['weekly_bias']} weekly. Short entry {a['entry_price']} / "
                          f"stop {a['stop_loss']} (above) / target {a['target_price']} (below) = "
                          f"{a['risk_reward']}:1, ~{a['expected_return_pct']}% if it falls."),
        }
        mtf_bias.apply_to_proposal(db, proposal, a)   # Lane 4 stamp + penalty + conflict log
        pid = db.insert_proposal(proposal)
        paper_trader.open_from_proposal(db, proposal, pid, analysis=a, config=config)
        stored += 1
    logger.info("Downside ideas: %d stored across %d negative sectors", stored, len(negative))
    return stored


def generate_coiling_ideas(
    config: dict[str, Any], db: Database, hot_sectors: list[str],
    turning_sectors: list[str], sector_analyzer: SectorAnalyzer,
) -> int:
    """Find names COILING before a breakout (squeeze + quiet accumulation) --
    the 'catch it before it runs' scan. Scope = hot sectors + laggard/turning
    sectors + the user's catalyst watchlist. Stored as `coiling` proposals."""
    c_cfg = config.get("technical", {}).get("coiling", {})
    if not c_cfg.get("enabled", True):
        return 0
    count = c_cfg.get("count", 10)
    max_price = c_cfg.get("max_price", 200)
    min_rr = c_cfg.get("min_risk_reward", 1.5)  # quality gate -- coiling had NO floor before

    symbol_sector: dict[str, str] = {}
    for sector in list(hot_sectors) + list(turning_sectors):
        for sym in sector_analyzer.candidates_for_sector(sector):
            symbol_sector.setdefault(sym, sector)

    coils: list[dict[str, Any]] = []
    for symbol, sector in symbol_sector.items():
        a = TECH.analyze_coiling(symbol)
        if not a or not a["is_coiling"] or a["entry_price"] > max_price:
            continue
        if a["risk_reward"] < min_rr:  # close the back door: enforce the R:R gate
            continue
        a["sector_name"] = sector
        coils.append(a)
    coils.sort(key=lambda a: a["coil_score"], reverse=True)
    top = coils[:count]

    risk_manager = RiskManager(config)
    agentic_max = config["accounts"]["agentic"]["price_range"][1]
    stored = 0
    for a in top:
        account_type = "agentic" if a["entry_price"] <= agentic_max else "personal"
        acct_cfg = config["accounts"][account_type]
        balance = (acct_cfg["starting_balance"] if acct_cfg.get("hide_balance")
                   else (db.get_account(account_type) or {}).get("current_balance")
                   or acct_cfg["starting_balance"])
        sizing = risk_manager.calculate_position_size(
            account_type=account_type, entry_price=a["entry_price"], stop_loss=a["stop_loss"],
            quality_score=a["quality_score"], account_balance=balance, risk_scale=0.75)
        if sizing is None:
            continue
        proposal = {
            "account_type": account_type, "symbol": a["symbol"], "sector_name": a["sector_name"],
            "entry_price": a["entry_price"], "stop_loss": a["stop_loss"], "target_price": a["target_price"],
            "risk_reward": a["risk_reward"], "quality_score": a["quality_score"],
            "confidence": a["confidence"], "num_edges": a["num_edges"], "edges_fired": a["edges_fired"],
            "strategy": "coiling",
            "position_size_usd": sizing["position_size_usd"], "shares": sizing["shares"],
            "risk_amount": sizing["risk_amount"], "expected_return_pct": a["expected_return_pct"],
            "expected_timeframe": a["expected_timeframe"],
            "reasoning": (f"COILING {a['symbol']} ({a['sector_name']}) -- coil score {a['coil_score']}/10: "
                          f"{a['edges_fired']}. Squeeze + accumulation while price is flat. "
                          f"Watch for breakout above {a['entry_price']}; target {a['target_price']}, "
                          f"stop {a['stop_loss']}."),
        }
        mtf_bias.apply_to_proposal(db, proposal, a)   # Lane 4 stamp + penalty + conflict log
        pid = db.insert_proposal(proposal)
        paper_trader.open_from_proposal(db, proposal, pid, analysis=a, config=config)
        stored += 1
    logger.info("Coiling ideas: %d stored (scanned %d names)", stored, len(symbol_sector))
    return stored


# ------------------------------------------------------------------- startup
CONFIG = load_config()
DB = Database(CONFIG["database"]["path"])
DB.seed_accounts(CONFIG["accounts"])
RH = RobinhoodClient(CONFIG)
ALPACA = AlpacaClient(CONFIG)
FINNHUB = FinnhubClient()   # key from .env only; disabled cleanly when absent
SECTOR_ANALYZER = SectorAnalyzer(CONFIG)
TECH = TechnicalAnalyzer(CONFIG)

app = FastAPI(title="Autonomous Trading System")
# The dashboard is served same-origin, so no cross-origin access is needed.
# Restricting this (was "*") stops other sites from calling the API in a
# visitor's authenticated browser session.
_ALLOWED_ORIGINS = CONFIG.get("auth", {}).get("allowed_origins", [])
app.add_middleware(
    CORSMiddleware, allow_origins=_ALLOWED_ORIGINS, allow_methods=["*"], allow_headers=["*"],
)

# --- lightweight in-memory rate limiting ----------------------------------
_scan_hits: dict[str, deque] = defaultdict(deque)
_auth_fails: dict[str, deque] = defaultdict(deque)
SCAN_LIMIT, SCAN_WINDOW = 3, 60          # max 3 scans / minute / IP
AUTH_FAIL_LIMIT, AUTH_WINDOW = 8, 300    # 8 bad logins / 5 min -> lockout


def _client_ip(request) -> str:
    fwd = request.headers.get("X-Forwarded-For")  # Cloudflare/tunnel sets this
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _too_many(bucket: dict[str, deque], ip: str, limit: int, window: int) -> bool:
    now = time.time()
    dq = bucket[ip]
    while dq and now - dq[0] > window:
        dq.popleft()
    if len(dq) >= limit:
        return True
    dq.append(now)
    return False


@app.middleware("http")
async def security_headers_and_limits(request, call_next):
    ip = _client_ip(request)
    # throttle the expensive scan / resolve endpoints per IP
    if request.method == "POST" and request.url.path in ("/api/scan", "/api/paper-trades/resolve"):
        if _too_many(_scan_hits, ip, SCAN_LIMIT, SCAN_WINDOW):
            return Response(status_code=429, content="Rate limit: too many scans, wait a minute.")
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'"
    )
    return response


@app.middleware("http")
async def no_cache_static(request, call_next):
    """Prevent the browser from serving stale dashboard assets so edits show
    up on a normal refresh (no hard-reload needed)."""
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".js", ".css", ".html")):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


# --- optional HTTP basic auth (for sharing the dashboard publicly) --------
_AUTH = CONFIG.get("auth", {})
AUTH_ENABLED = os.environ.get("DASH_AUTH", "1" if _AUTH.get("enabled") else "0") == "1"
AUTH_USER = os.environ.get("DASH_USER", _AUTH.get("username", "trader"))
AUTH_PASS = os.environ.get("DASH_PASS", _AUTH.get("password", ""))


@app.middleware("http")
async def basic_auth(request, call_next):
    # /api/health stays open so uptime checks (and the tunnel) can probe it.
    if AUTH_ENABLED and request.url.path != "/api/health":
        ip = _client_ip(request)
        # lock out an IP that's been guessing the password
        now = time.time()
        fails = _auth_fails[ip]
        while fails and now - fails[0] > AUTH_WINDOW:
            fails.popleft()
        if len(fails) >= AUTH_FAIL_LIMIT:
            return Response(status_code=429, content="Too many failed logins. Try again later.")

        header = request.headers.get("Authorization", "")
        authorized = False
        if header.startswith("Basic "):
            try:
                user, _, pwd = base64.b64decode(header[6:]).decode().partition(":")
                authorized = (secrets.compare_digest(user, AUTH_USER)
                              and secrets.compare_digest(pwd, AUTH_PASS))
            except Exception:
                authorized = False
        if not authorized:
            fails.append(now)
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Dashboard"'})
    return await call_next(request)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "robinhood_authenticated": RH.authenticated,
            "dry_run": RH.dry_run, "alpaca_live": ALPACA.enabled}


@app.get("/api/live")
def get_live() -> dict[str, Any]:
    """Live mark of every open paper trade against Alpaca's real-time feed:
    live price, live P&L, distance to the frozen stop/target, RS-vs-SPY, and a
    bar-age stamp on every price. Polled by the dashboard every ~5s."""
    return live_module.build_live_snapshot(DB, ALPACA)


@app.get("/api/regime")
def get_regime() -> dict[str, Any]:
    regime = DB.get_latest_market_regime()
    if regime is None:
        raise HTTPException(404, "No market regime data yet -- run a scan first")
    return regime


@app.get("/api/sectors")
def get_sectors(limit: int = 40) -> list[dict[str, Any]]:
    return DB.get_latest_sector_rankings(limit=limit)


@app.get("/api/sector/{sector_name}/setups")
def sector_setups(
    sector_name: str,
    limit: int = 5,
    horizon: str = "swing",
    direction: str = "long",
    max_price: Optional[float] = None,
) -> dict[str, Any]:
    """On-demand: run the SAME edge-stack rules as the main scan across a
    single sector's candidate tickers and return its top setups.

    - direction='long'  -> bullish setups (upside)
    - direction='short' -> bearish setups (downside, mirror edges)
    - horizon='swing'   -> weekly-anchored swing (long only)
    - horizon='short'   -> daily+4h breakout, 1-3 day (long only)
    - max_price         -> only names at/under this price (e.g. 50)
    Selectivity adapts: a strong sector is lenient for longs / strict for
    shorts, and a weak (negative) sector is lenient for shorts."""
    candidates = SECTOR_ANALYZER.candidates_for_sector(sector_name)
    if not candidates:
        raise HTTPException(404, f"Unknown sector '{sector_name}'")

    rankings = DB.get_latest_sector_rankings()
    score = next((r["composite_score"] for r in rankings if r["sector_name"] == sector_name), None)
    hot_threshold = CONFIG.get("sectors", {}).get("hot_threshold", 3.0)
    s = score if score is not None else 0.0
    if direction == "short":
        # a sufficiently NEGATIVE sector is the "hot" one for shorting
        selectivity = "LOW" if s <= -hot_threshold else "MEDIUM"
    else:
        selectivity = "LOW" if s >= hot_threshold else "MEDIUM"
    min_rank = TIER_RANK[selectivity]

    setups: list[dict[str, Any]] = []
    for symbol in candidates:
        if direction == "short":
            a = TECH.analyze_downside(symbol)
        else:
            a = TECH.analyze_short_term(symbol) if horizon == "short" else TECH.analyze(symbol)
        if not a or TIER_RANK.get(a["confidence"], 0) < min_rank or a["risk_reward"] < 1.0:
            continue
        if max_price and a["entry_price"] > max_price:  # 0/None = no cap
            continue
        setups.append({
            "symbol": a["symbol"], "confidence": a["confidence"], "num_edges": a["num_edges"],
            "edges_fired": a["edges_fired"], "quality_score": a["quality_score"],
            "entry_price": a["entry_price"], "stop_loss": a["stop_loss"],
            "target_price": a["target_price"], "risk_reward": a["risk_reward"],
            "expected_return_pct": a["expected_return_pct"], "rsi": a["rsi"],
            "macd_signal": a["macd_signal"], "bb_position": a["bb_position"],
            "rvol": a["rvol"], "patterns": a["patterns"], "direction": direction,
            "daily_bias": a["daily_bias"], "weekly_bias": a["weekly_bias"],
        })

    setups.sort(key=lambda s: (TIER_RANK[s["confidence"]], s["num_edges"], s["quality_score"]),
                reverse=True)
    return {"sector": sector_name, "composite_score": score, "selectivity": selectivity,
            "horizon": horizon, "direction": direction, "max_price": max_price,
            "candidates_scanned": len(candidates), "setups": setups[:limit]}


@app.get("/api/proposals")
def get_proposals(status: Optional[str] = None, account_type: Optional[str] = None) -> list[dict[str, Any]]:
    return DB.get_proposals(status=status, account_type=account_type)


@app.post("/api/proposals/{proposal_id}/approve")
def approve_proposal(proposal_id: int) -> dict[str, Any]:
    """Human-in-the-loop execution gate: calling this endpoint IS the
    manual approval. It places (or, in dry_run, simulates) the order."""
    proposal = DB.get_proposal(proposal_id)
    if proposal is None:
        raise HTTPException(404, "Proposal not found")
    if proposal["status"] != "pending":
        raise HTTPException(400, f"Proposal already {proposal['status']}")

    order = RH.place_market_order(
        symbol=proposal["symbol"], quantity=proposal["shares"], side="buy", confirm=True,
    )
    if order.get("status") == "failed":
        DB.update_proposal_status(proposal_id, "failed")
        raise HTTPException(502, f"Order failed: {order.get('error')}")

    DB.update_proposal_status(proposal_id, "executed", order_id=order.get("order_id"))
    trade_id = DB.insert_trade({
        "proposal_id": proposal_id,
        "account_type": proposal["account_type"],
        "symbol": proposal["symbol"],
        "side": "buy",
        "quantity": proposal["shares"],
        "entry_price": proposal["entry_price"],
        "exit_price": None,
        "entry_time": datetime.now(timezone.utc).isoformat(),
        "exit_time": None,
        "pnl": None,
        "pnl_pct": None,
        "status": "open",
        "order_id": order.get("order_id"),
    })
    DB.upsert_position({
        "account_type": proposal["account_type"],
        "symbol": proposal["symbol"],
        "quantity": proposal["shares"],
        "avg_price": proposal["entry_price"],
        "current_price": proposal["entry_price"],
        "market_value": proposal["shares"] * proposal["entry_price"],
        "unrealized_pnl": 0,
        "unrealized_pnl_pct": 0,
    })

    account = DB.get_account(proposal["account_type"])
    if account:
        new_balance = account["current_balance"] - proposal["position_size_usd"]
        DB.update_account_balance(proposal["account_type"], new_balance)

    return {"trade_id": trade_id, "order": order}


@app.post("/api/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: int) -> dict[str, Any]:
    proposal = DB.get_proposal(proposal_id)
    if proposal is None:
        raise HTTPException(404, "Proposal not found")
    if proposal["status"] != "pending":
        raise HTTPException(400, f"Proposal already {proposal['status']}")
    DB.update_proposal_status(proposal_id, "rejected")
    return {"status": "rejected"}


@app.get("/api/trades")
def get_trades(account_type: Optional[str] = None, status: Optional[str] = None) -> list[dict[str, Any]]:
    return DB.get_trades(account_type=account_type, status=status)


@app.get("/api/positions")
def get_positions(account_type: Optional[str] = None) -> list[dict[str, Any]]:
    positions = DB.get_positions(account_type=account_type)
    for pos in positions:
        quote = RH.get_quote(pos["symbol"])
        if quote:
            pos["current_price"] = quote["price"]
            pos["market_value"] = pos["quantity"] * quote["price"]
            pos["unrealized_pnl"] = pos["market_value"] - (pos["quantity"] * pos["avg_price"])
            if pos["avg_price"]:
                pos["unrealized_pnl_pct"] = round(
                    (quote["price"] - pos["avg_price"]) / pos["avg_price"] * 100, 2
                )
    return positions


@app.get("/api/accounts")
def get_accounts() -> list[dict[str, Any]]:
    accounts = []
    for a in CONFIG["accounts"]:
        row = DB.get_account(a)
        if not row:
            continue
        d = dict(row)
        # Never send the dollar balance to the UI for hidden accounts.
        if CONFIG["accounts"][a].get("hide_balance"):
            d["current_balance"] = None
            d["starting_balance"] = None
            d["hidden"] = True
        accounts.append(d)
    return accounts


@app.get("/api/performance")
def get_performance(account_type: Optional[str] = None) -> list[dict[str, Any]]:
    rows = DB.get_performance(account_type=account_type)
    for row in rows:
        if CONFIG["accounts"].get(row["account_type"], {}).get("hide_balance"):
            row["total_value"] = None
            row["cash"] = None
            row["hidden"] = True
    return rows


@app.get("/api/track-record")
def get_track_record() -> dict[str, Any]:
    closed = [t for t in DB.get_paper_trades() if t["status"] == "closed"]
    wins = [t for t in closed if t["outcome"] == "win"]
    overall = {
        "n": len(closed),
        "win_rate": round(100 * len(wins) / len(closed), 1) if closed else 0.0,
        "avg_return": round(sum(t["return_pct"] or 0 for t in closed) / len(closed), 2) if closed else 0.0,
    }
    return {
        "overall": overall,
        "by_tier": DB.get_track_record(),
        "edges": DB.get_edge_performance(),
        "open": len(DB.get_paper_trades(status="open")),
        "closed": len(closed),
        "recent_closed": sorted(closed, key=lambda t: t.get("exit_date") or "", reverse=True)[:15],
    }


@app.get("/api/paper-trades")
def get_paper_trades(status: Optional[str] = None) -> list[dict[str, Any]]:
    return DB.get_paper_trades(status=status)


@app.post("/api/paper-trades/resolve")
def resolve_paper_trades() -> dict[str, Any]:
    return paper_trader.resolve_open(DB)


@app.get("/api/watchlist")
def get_watchlist() -> list[dict[str, Any]]:
    return DB.get_watchlist()


@app.post("/api/watchlist")
def add_watchlist(symbol: str, note: str = "") -> dict[str, Any]:
    DB.add_watchlist(symbol, note)
    return {"ok": True, "watchlist": DB.get_watchlist()}


@app.delete("/api/watchlist/{symbol}")
def remove_watchlist(symbol: str) -> dict[str, Any]:
    DB.remove_watchlist(symbol)
    return {"ok": True, "watchlist": DB.get_watchlist()}


@app.get("/api/turning-sectors")
def get_turning_sectors() -> list[str]:
    return SectorAnalyzer.turning_sectors(DB.get_latest_sector_rankings())


@app.post("/api/scan")
def trigger_scan() -> dict[str, Any]:
    return run_full_scan(CONFIG, DB, RH)


# --------------------------------------------------------------- autonomous engine
# Replaces the manual "Run Scan": scans on a cadence + continuously monitors and
# closes open positions at target/stop. Set env DASH_NO_SCHED=1 to disable (e.g.
# during tests). Opening trades is simulated unless autonomous.auto_execute=true.
SCHEDULER = AutonomousScheduler(CONFIG, DB, ALPACA, lambda: run_full_scan(CONFIG, DB, RH),
                                finnhub=FINNHUB)


@app.on_event("startup")
def _start_scheduler() -> None:
    if os.environ.get("DASH_NO_SCHED") == "1":
        logger.info("Autonomous scheduler suppressed via DASH_NO_SCHED=1")
        return
    SCHEDULER.start()


@app.on_event("shutdown")
def _stop_scheduler() -> None:
    SCHEDULER.stop()


@app.get("/api/scheduler")
def scheduler_status() -> dict[str, Any]:
    return SCHEDULER.status()


@app.get("/api/market-bias")
def get_market_bias() -> dict[str, Any]:
    """Lane 4 panel: weekly bias for SPY/QQQ/IWM/DIA/RSP + 11 SPDRs + Mag7,
    RS vs SPY, 20w-EMA distance, weekly squeeze, and the regime roll-up.
    Cache read only -- the scheduler/scan refreshes it (TTL ~12h)."""
    hit = DB.cache_get(mtf_bias.PANEL_KEY)
    if not hit:
        return {"regime": None, "indexes": [], "sectors": [], "mag7": [],
                "as_of": None, "stale": True}
    return {**hit["payload"], "stale": (hit.get("age_seconds") or 0) > 24 * 3600}


# ---- Phase 4: Finnhub-backed cached news/earnings routes (cache reads ONLY;
# the background refresher is the sole caller of Finnhub; display-only data) ----
def _cached_news(key: str) -> dict[str, Any]:
    hit = DB.cache_get(key)
    return {"items": (hit or {}).get("payload") or [],
            "fetched_at": (hit or {}).get("fetched_at"),
            "stale": hit is None or (hit.get("age_seconds") or 1e9) > 3600,
            "finnhub_enabled": FINNHUB.enabled}


@app.get("/api/news/market")
def news_market() -> dict[str, Any]:
    return _cached_news("news:market")


@app.get("/api/news/symbol/{ticker}")
def news_symbol(ticker: str) -> dict[str, Any]:
    news_refresher.register_interest("symbol", ticker)   # lazy refresh registration
    return _cached_news(f"news:symbol:{ticker.upper()}")


@app.get("/api/news/sector/{etf}")
def news_sector(etf: str) -> dict[str, Any]:
    news_refresher.register_interest("sector", etf)
    return _cached_news(f"news:sector:{etf.upper()}")


@app.get("/api/earnings/upcoming")
def earnings_upcoming(days: int = 14) -> dict[str, Any]:
    hit = DB.cache_get("earnings:calendar")
    rows = []
    if hit:
        today = datetime.now(timezone.utc).date()
        for e in (hit["payload"] or {}).get("earningsCalendar", []):
            try:
                d = datetime.fromisoformat(e.get("date", "")).date()
            except (TypeError, ValueError):
                continue
            delta = (d - today).days
            if 0 <= delta <= days:
                rows.append({"symbol": e.get("symbol"), "date": e.get("date"),
                             "days_away": delta, "hour": e.get("hour"),
                             "eps_estimate": e.get("epsEstimate")})
    rows.sort(key=lambda r: (r["days_away"], r["symbol"] or ""))
    return {"days": days, "count": len(rows), "earnings": rows,
            "fetched_at": (hit or {}).get("fetched_at"), "finnhub_enabled": FINNHUB.enabled}


@app.get("/api/drilldown/{symbol}")
def get_drilldown(symbol: str) -> dict[str, Any]:
    """Timeframe-by-timeframe (15m/30m/1h/4h/daily) bias + a trade plan only when
    the compression + MACD-cross + pivot confluence is genuinely there."""
    return drilldown_module.build(ALPACA, symbol.upper())


@app.get("/api/market-overview")
def get_market_overview() -> dict[str, Any]:
    """Expanded Market Regime panel: indices (SPY/QQQ/IWM), VIX, breadth proxy,
    economic calendar (static), earnings for held names, and market news."""
    held = sorted({t["symbol"] for t in DB.get_paper_trades(status="open")})
    return market_overview_module.build(ALPACA, DB.get_latest_sector_rankings(), CONFIG, held)


@app.get("/api/bias-strip")
def get_bias_strip() -> dict[str, Any]:
    """SPY + mega-caps: live price, conditional bias, and key level above/below.
    Powers the dashboard's top Market Bias strip (cached structure + live price)."""
    mega = CONFIG.get("dashboard", {}).get(
        "bias_strip", ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA"])
    symbols = ["SPY"] + [s for s in mega if s != "SPY"]
    return {"as_of": datetime.now(timezone.utc).isoformat(),
            "alpaca_enabled": ALPACA.enabled,
            "symbols": bias_strip_module.build(ALPACA, symbols)}


@app.get("/api/log/algo")
def get_algo_log(status: Optional[str] = None,
                 sort: Optional[str] = None, dir: str = "desc",
                 setup: Optional[str] = None, direction: Optional[str] = None,
                 band: Optional[str] = None, outcome: Optional[str] = None,
                 exit_reason: Optional[str] = None, quadrant: Optional[str] = None,
                 sector: Optional[str] = None, market_regime: Optional[str] = None) -> dict[str, Any]:
    """Autonomous Algo book (Log B): every scanner-opened trade with its process
    grade + classification, newest first. `open` / `closed` filterable. Each row
    is enriched from its originating proposal so R:R / quality / edges / rationale
    are present even on legacy rows that predate the grade columns.

    Lane 5 additions (all optional/additive; response shape unchanged): `sort` +
    `dir` (allowlisted server-side), and comma-separable facet params (setup,
    direction, band, outcome, exit_reason, quadrant, sector, market_regime)."""
    raw = {"setup": setup, "direction": direction, "band": band, "outcome": outcome,
           "exit_reason": exit_reason, "quadrant": quadrant, "sector": sector,
           "market_regime": market_regime}
    facets = {k: v.split(",") for k, v in raw.items() if v}
    trades = DB.get_algo_trades(status=status, sort=sort, direction=dir,
                                facets=facets or None)
    for t in trades:
        # display R:R: the trade's own planned_rr, else the proposal's R:R
        t["risk_reward"] = t.get("planned_rr") if t.get("planned_rr") is not None \
            else t.get("proposal_risk_reward")
        t["quality_score"] = t.get("proposal_quality_score")
        if not t.get("edges_fired"):
            t["edges_fired"] = t.get("proposal_edges_fired")
        t["reasoning"] = t.get("proposal_reasoning")
        # legacy = opened before the grading path existed (no grade recorded)
        t["legacy"] = t.get("process_grade") is None
    graded = sum(1 for t in trades if t.get("process_grade") and t["process_grade"] != "UNGRADED")
    ungraded = sum(1 for t in trades if t.get("process_grade") == "UNGRADED")
    legacy = sum(1 for t in trades if t["legacy"])
    return {"count": len(trades), "graded": graded, "ungraded": ungraded,
            "legacy": legacy, "trades": trades}


if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
