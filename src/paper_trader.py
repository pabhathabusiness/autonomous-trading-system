"""
Automatic paper-trading simulation + feedback loop.

Every proposal the system generates is opened as a simulated trade (whether
or not the user clicks Approve). A resolver then replays real price action
since entry to decide whether each trade hit its target (win), its stop
(loss), or timed out -- building an honest track record of how the strategy
and each confidence tier actually perform. That record is the feedback loop:
which setups and which edges genuinely precede winners.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import yfinance as yf

from src import process_grader
from src.database import Database

logger = logging.getLogger(__name__)

# archetype -> the entry_type label the journal shows
_ENTRY_TYPE = {
    "trending_pullback_to_pivot": "pullback-zone",
    "reversal": "reversal-break",
    "breakout_continuation": "breakout/retest",
}

# fields an analysis MUST carry to be gradeable; missing => UNGRADED (bright flag)
_GRADEABLE_FIELDS = ("archetype", "dim_scores", "rs_vs_spy")


def grade_fields(analysis: dict | None, *, model: str, sector_name: str | None,
                 config: dict | None, db: Database) -> dict:
    """Process-grade an analysis at open time -> the journal/grade columns.

    Fails SOFT: if the analysis is missing the fields the grader needs (an
    engine not yet refactored), the trade is logged UNGRADED rather than
    silently blank -- a bright flag in the UI, never mistaken for a real grade.
    """
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

    # sector context: is this a mega-cap sector leader (carve-out), and how is
    # its sector ranked right now?
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


def _max_hold_days(timeframe: str) -> int:
    tf = (timeframe or "").lower()
    if "2-6 week" in tf:
        return 42
    if "1-3 week" in tf:
        return 21
    if "3-10 day" in tf:
        return 12
    if "day" in tf:  # short-term "1-2 days" / "1-3 days"
        return 4
    return 21


def open_from_proposal(db: Database, proposal: dict, proposal_id: int, *,
                       book: str = "algo", source: str = "algo",
                       analysis: dict | None = None, config: dict | None = None) -> None:
    """Open a simulated trade mirroring a proposal (idempotent per proposal).

    Autonomous (scanner-opened) trades are the Autonomous Algo book (Log B):
    tagged book='algo' and stamped with their process grade at open, so the
    graded log is a faithful window into what the engine is doing -- required
    now that no human approves each trade. `analysis` is the analyze() dict the
    proposal came from (carries archetype/dim_scores/rs_vs_spy for grading).
    """
    gf = grade_fields(analysis, model=proposal.get("strategy", "swing"),
                      sector_name=proposal.get("sector_name"), config=config, db=db)
    shares = proposal.get("shares")
    entry = proposal["entry_price"]
    db.open_paper_trade({
        "proposal_id": proposal_id,
        "symbol": proposal["symbol"],
        "account_type": proposal.get("account_type"),
        "strategy": proposal.get("strategy", "swing"),
        "direction": proposal.get("direction", "long"),
        "confidence": proposal.get("confidence"),
        "num_edges": proposal.get("num_edges"),
        "edges_fired": proposal.get("edges_fired"),
        "sector_name": proposal.get("sector_name"),
        "entry_price": entry,
        "stop_loss": proposal["stop_loss"],
        "target_price": proposal["target_price"],
        "expected_timeframe": proposal.get("expected_timeframe"),
        "max_hold_days": _max_hold_days(proposal.get("expected_timeframe", "")),
        "book": book, "source": source,
        "shares": shares,
        "position_value": round(shares * entry, 2) if shares and entry else None,
        # Lane 4: regime + MTF context stamped by mtf_bias.apply_to_proposal
        "market_regime": proposal.get("market_regime"),
        "mtf_alignment": proposal.get("mtf_alignment"),
        **gf,
    })
    if gf.get("process_grade") == "UNGRADED":
        logger.warning("UNGRADED open: %s (%s) -- analysis missing grade fields",
                       proposal.get("symbol"), proposal.get("strategy"))


def resolve_open(db: Database) -> dict[str, int]:
    """Replay price action for every open paper trade and close the ones that
    hit target/stop or aged out. Returns a summary of what changed."""
    open_trades = db.get_paper_trades(status="open")
    summary = {"checked": len(open_trades), "wins": 0, "losses": 0, "expired": 0, "still_open": 0}

    for t in open_trades:
        try:
            entry_dt = datetime.fromisoformat(t["entry_date"])
        except (ValueError, TypeError):
            continue
        entry = t["entry_price"]
        stop = t["stop_loss"]
        target = t["target_price"]
        now = datetime.now(timezone.utc)
        days_held = (now - entry_dt).days

        try:
            hist = yf.Ticker(t["symbol"]).history(
                start=entry_dt.date().isoformat(), interval="1d", auto_adjust=True)
        except Exception as exc:
            logger.debug("resolve %s failed: %s", t["symbol"], exc)
            summary["still_open"] += 1
            continue
        if hist is None or hist.empty:
            summary["still_open"] += 1
            continue

        is_short = t.get("direction") == "short"
        # for a short: target is BELOW entry, stop is ABOVE; a win is price
        # falling to target, a loss is price rising to stop. return is the
        # gain to the short (entry - exit) / entry.
        def ret_at(exit_price: float) -> float:
            return ((entry - exit_price) if is_short else (exit_price - entry)) / entry * 100

        resolved = False
        for _, bar in hist.iterrows():
            if is_short:
                hit_target = bar["Low"] <= target
                hit_stop = bar["High"] >= stop
            else:
                hit_target = bar["High"] >= target
                hit_stop = bar["Low"] <= stop
            if hit_stop and hit_target:  # both same bar -> assume stop first
                db.close_paper_trade(t["id"], stop, ret_at(stop), "loss", "closed")
                summary["losses"] += 1
                resolved = True
                break
            if hit_target:
                db.close_paper_trade(t["id"], target, ret_at(target), "win", "closed")
                summary["wins"] += 1
                resolved = True
                break
            if hit_stop:
                db.close_paper_trade(t["id"], stop, ret_at(stop), "loss", "closed")
                summary["losses"] += 1
                resolved = True
                break
        if resolved:
            continue

        # timed out -> close at the latest close, count by sign of return
        if days_held >= (t["max_hold_days"] or 21):
            last_close = float(hist["Close"].iloc[-1])
            ret = ret_at(last_close)
            db.close_paper_trade(t["id"], last_close, ret, "win" if ret > 0 else "loss", "closed")
            summary["expired"] += 1
        else:
            summary["still_open"] += 1

    logger.info("Paper-trade resolution: %s", summary)
    return summary
