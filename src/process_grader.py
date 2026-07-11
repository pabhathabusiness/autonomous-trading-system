"""
Process grader -- scores DECISION QUALITY, never outcome.

Core philosophy (locked with the user): grade the process, not the P&L. Money
is the byproduct. Every rule here is machine-checkable from the setup at entry
time and is completely independent of whether the trade later won or lost. The
same A-grade is awarded to a disciplined entry that happens to lose as to one
that happens to win -- that separation is the whole point, so the feedback
review can later ask "do high-process trades win more over time?".

`grade()` is a pure function: it takes an `analyze()` result dict plus a little
sector context and returns `{grade, score, flags, notes, subscores}`.

Grading is ARCHETYPE-AWARE (the three setups reward different disciplines):
  * trending_pullback_to_pivot -> reward WAITING at the pivot, penalize chasing
  * reversal                    -> reward the CONFIRMED break at the key level
  * breakout_continuation       -> reward entry ON the confirmed break, not
                                   anticipation

and it encodes the timeframe hierarchy (higher TF = permission; a lower-TF
entry against the higher-TF bias is penalized) and rewards breadth across the
five capped dimensions rather than a single raging-momentum read.
"""

from __future__ import annotations

from typing import Any, Optional

# R:R floor per model/horizon -- the gate the trade must clear to grade well.
_RR_FLOOR = {"swing": 1.5, "short": 1.5, "coiling": 1.5, "downside": 1.5}

# weightings (sum to 100). entry_discipline is the headline process signal.
_WEIGHTS = {
    "entry_discipline": 26,
    "timeframe_confluence": 18,
    "confluence_breadth": 16,
    "stop_at_structure": 14,
    "rr_quality": 12,
    "sector_alignment": 8,
    "rel_strength": 6,
}


def _letter(score: float) -> str:
    if score >= 88:
        return "A"
    if score >= 78:
        return "B"
    if score >= 68:
        return "C"
    if score >= 55:
        return "D"
    return "F"


def _rr_quality(rr: float, floor: float) -> tuple[float, list[str]]:
    if rr <= 0:
        return 0.0, ["no_rr"]
    if rr < 1.0:
        return 0.15, ["weak_rr"]
    if rr < floor:
        return 0.5, ["thin_rr"]
    if rr < 2.0:
        return 0.8, []
    return 1.0, ["strong_rr"]


def _entry_discipline(archetype: str, direction: str, entry: float,
                      support: Optional[float], patterns: list[str],
                      compression_dir: Optional[str], bb_breakout: bool
                      ) -> tuple[float, list[str]]:
    """The archetype-specific 'did we take the RIGHT kind of entry' read."""
    pat_blob = " ".join(patterns).lower()
    # distance from entry back to the demand/supply pivot we should be leaning on
    dist = abs(entry - support) / entry if (support and entry) else None

    if archetype == "breakout_continuation":
        # reward entry ON a confirmed break, not anticipation of one
        if compression_dir or bb_breakout:
            return 1.0, ["confirmed_break"]
        if "squeeze" in pat_blob or "pennant" in pat_blob or "triangle" in pat_blob:
            return 0.5, ["anticipating_break"]
        return 0.35, ["no_break_confirm"]

    if archetype == "reversal":
        reversal_pat = any(p in pat_blob for p in
                           ("falling wedge", "double bottom", "inverse head", "inverse h&s"))
        at_level = dist is not None and dist <= 0.04
        if reversal_pat and at_level:
            return 1.0, ["confirmed_reversal_at_level"]
        if reversal_pat or at_level:
            return 0.6, ["partial_reversal_confirm"]
        return 0.3, ["anticipating_reversal"]

    # default: trending_pullback_to_pivot -- reward buying INTO the pivot
    if dist is None:
        return 0.4, ["no_pivot_reference"]
    if dist <= 0.03:
        return 1.0, ["waited_at_pivot"]
    if dist <= 0.06:
        return 0.7, []
    return 0.3, ["chased_entry"]


def _stop_at_structure(direction: str, entry: float, stop: float,
                       support: Optional[float], min_stop_pct: float
                       ) -> tuple[float, list[str]]:
    if not entry or not stop:
        return 0.4, ["no_stop"]
    stop_dist = abs(entry - stop) / entry
    if stop_dist < min_stop_pct * 0.6:
        return 0.4, ["stop_too_tight"]
    # is the stop actually parked beyond a real structural level?
    if support:
        beyond = stop <= support * 1.001 if direction != "short" else stop >= support * 0.999
        if beyond:
            return 1.0, ["stop_at_structure"]
        return 0.7, []
    return 0.6, ["stop_on_floor"]


def _confluence_breadth(dim_scores: dict[str, float], num_edges: int
                        ) -> tuple[float, list[str]]:
    """Reward breadth ACROSS the five capped dimensions -- the point of the
    rebalance -- not depth in a single one."""
    active = sum(1 for v in (dim_scores or {}).values() if v and v > 0)
    if active >= 4:
        base = 1.0
    elif active == 3:
        base = 0.75
    elif active == 2:
        base = 0.5
    else:
        base = 0.3
    flags = []
    if active <= 1:
        flags.append("thin_confluence")
    elif active >= 4:
        flags.append("broad_confluence")
    # a tiny nudge so a genuinely deep stack isn't punished vs a shallow one
    if num_edges and num_edges >= 8:
        base = min(1.0, base + 0.05)
    return base, flags


def _timeframe_confluence(direction: str, daily_bias: str, weekly_bias: str
                          ) -> tuple[float, list[str]]:
    """Higher TF is permission. Aligned across daily+weekly = full marks; a
    lower-TF trade taken against the bigger bias is penalized."""
    want = "BEARISH" if direction == "short" else "BULLISH"
    against = "BULLISH" if direction == "short" else "BEARISH"
    d_ok, w_ok = daily_bias == want, weekly_bias == want
    d_bad, w_bad = daily_bias == against, weekly_bias == against
    if d_bad or w_bad:
        return 0.3, ["counter_bias"]
    if d_ok and w_ok:
        return 1.0, ["full_tf_confluence"]
    if d_ok or w_ok:
        return 0.7, []
    return 0.5, []  # both neutral -- permitted but unconfirmed


def _sector_alignment(direction: str, sector_score: Optional[float],
                      is_sector_leader: bool) -> tuple[float, list[str]]:
    # MAG-7 / mega-cap carve-out: sector leaders ARE the sector -> self-driven,
    # skip sector-sentiment gating entirely.
    if is_sector_leader:
        return 1.0, ["sector_leader_self_driven"]
    if sector_score is None:
        return 0.7, []
    favorable = sector_score < 0 if direction == "short" else sector_score > 0
    adverse = sector_score > 0 if direction == "short" else sector_score < 0
    if favorable:
        return 1.0, []
    if adverse:
        return 0.4, ["sector_misaligned"]
    return 0.7, []


def _rel_strength(direction: str, rs_vs_spy: Optional[float]) -> tuple[float, list[str]]:
    if rs_vs_spy is None:
        return 0.6, []
    favorable = rs_vs_spy < 0 if direction == "short" else rs_vs_spy > 0
    if favorable:
        return 1.0, ["rs_favorable"]
    if abs(rs_vs_spy) < 1.0:
        return 0.55, []
    return 0.3, ["rs_adverse"]


def grade(analysis: dict[str, Any], *, model: str = "swing",
          sector_score: Optional[float] = None,
          is_sector_leader: bool = False,
          min_stop_pct: float = 0.025) -> dict[str, Any]:
    """Grade one setup's process quality. Pure + outcome-independent.

    `analysis` is a `TechnicalAnalyzer.analyze*()` result. Missing fields fall
    back to conservative-neutral so a partial dict never crashes grading.
    """
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

    def run(key: str, result: tuple[float, list[str]]) -> None:
        score, fl = result
        subs[key] = round(score, 3)
        flags.extend(fl)

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

    # a short human note keyed off the dominant driver / worst offender
    if "chased_entry" in flags:
        note = "Chased -- entry stretched from the pivot."
    elif "counter_bias" in flags:
        note = "Taken against the higher-timeframe bias."
    elif "waited_at_pivot" in flags:
        note = "Disciplined -- waited at the pivot."
    elif "confirmed_break" in flags:
        note = "Entered on the confirmed break."
    elif "confirmed_reversal_at_level" in flags:
        note = "Confirmed reversal at the key level."
    elif "thin_confluence" in flags:
        note = "Thin -- confluence in too few dimensions."
    else:
        note = f"{letter}-grade process ({score:.0f}/100)."

    return {
        "grade": letter,
        "score": score,
        "flags": flags,
        "notes": note,
        "subscores": subs,
        "archetype": archetype,
    }
