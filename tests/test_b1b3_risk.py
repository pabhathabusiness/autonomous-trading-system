"""
B1+B3 test suite -- the precondition for ever flipping alpaca.auto_place ON.

Covers: the 7 risk-gate controls, the submit_bracket_order chokepoint (can't
place without an approved decision bound to symbol+qty; paper-api assert), fill
parsing (partial / reject / gap-through-stop / slippage), the daily-loss +
drawdown halts incl. persistence across restart, order_executor batch behavior
(halt/no-equity fail-safe, within-batch caps, idempotency), and the sim_vs_real
view.

Runs with plain `py tests/test_b1b3_risk.py` (no pytest needed) or under pytest.
"""
import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import risk_gate, risk_state, fill_recorder, order_executor, execution_guard
from src.risk_gate import RiskContext, RiskDecision, RiskGateError
from src.database import Database
from src.risk_manager import RiskManager


# ----------------------------------------------------------------- fixtures
def make_config():
    return {
        "accounts": {"algo": {"starting_balance": 100000, "max_risk_per_trade_pct": 1.0,
                              "quality_threshold": 7.5}},
        "alpaca": {"paper_only": True, "paper_url": "https://paper-api.alpaca.markets"},
        "autonomous": {"auto_execute_accounts": ["algo"]},
        "risk": {"max_open_risk_pct": 5.0, "daily_loss_limit_pct": -2.0,
                 "drawdown_kill_pct": -10.0, "per_lane_cap_pct": 30.0,
                 "max_positions_per_sector": 3, "liquidity_max_adv_participation_pct": 1.0,
                 "liquidity_min_price": 0.20, "liquidity_min_dollar_vol": 300000},
    }


def base_ctx(**over):
    d = dict(account_type="algo", symbol="TEST", equity=100000.0, entry=3.0, stop=2.7,
             target=3.6, shares=3333, sector="Technology", lane="turnaround",
             config=make_config(), open_risk=0.0, sector_counts={}, lane_notional={},
             halted=False, avg_dollar_vol=5_000_000.0, rel_vol=2.0, days_to_earnings=10)
    d.update(over)
    return RiskContext(**d)


def fresh_db():
    path = os.path.join(tempfile.gettempdir(), f"b1b3_{uuid.uuid4().hex}.db")
    return Database(path), path


class FakeAlpaca:
    """Mimics the real client's contract INCLUDING the fail-closed chokepoint."""
    def __init__(self, equity, config, fills=None):
        self._equity, self._config = equity, config
        self.paper_url = "https://paper-api.alpaca.markets"
        self.enabled = True
        self._fills = fills or {}
        self.placed = []

    def account_equity(self):
        return self._equity

    def submit_bracket_order(self, *, symbol, qty, side, entry_price, stop_price,
                             target_price, account_type, risk_decision,
                             client_order_id=None, **kw):
        execution_guard.assert_paper_execution(
            account_type=account_type, endpoint_url=self.paper_url, config=self._config)
        risk_gate.assert_trade_allowed(risk_decision, symbol=symbol, qty=int(qty))
        self.placed.append(symbol)
        return {"id": f"ord-{symbol}", "status": "accepted", "client_order_id": client_order_id}

    def get_order(self, oid):
        return self._fills.get(oid)


def _raises(exc, fn, *a, **k):
    try:
        fn(*a, **k)
    except exc:
        return True
    except Exception as other:
        raise AssertionError(f"expected {exc.__name__}, got {type(other).__name__}: {other}")
    raise AssertionError(f"expected {exc.__name__}, nothing raised")


# ------------------------------------------------------------- risk-gate controls
def test_gate_approves_clean():
    d = risk_gate.evaluate(base_ctx())
    assert d.approved, d.reason
    assert abs(d.risk_pct - 1.0) < 0.05, d.risk_pct        # ~1% of equity at risk


def test_gate_position_sizing_fail():
    assert not risk_gate.evaluate(base_ctx(shares=0)).checks["position_sizing"]
    assert not risk_gate.evaluate(base_ctx(equity=None)).checks["position_sizing"]
    assert not risk_gate.evaluate(base_ctx(entry=3.0, stop=3.0)).checks["position_sizing"]


def test_gate_max_open_risk():
    # existing open risk 4600 + this ~1000 = 5.6% > 5%
    d = risk_gate.evaluate(base_ctx(open_risk=4600.0))
    assert not d.checks["max_open_risk"] and not d.approved


def test_gate_per_lane_cap():
    d = risk_gate.evaluate(base_ctx(lane_notional={"turnaround": 25000.0}))
    assert not d.checks["per_lane_cap"] and not d.approved


def test_gate_sector_cap():
    d = risk_gate.evaluate(base_ctx(sector_counts={"Technology": 3}))
    assert not d.checks["sector_cap"] and not d.approved
    assert risk_gate.evaluate(base_ctx(sector_counts={"Technology": 2})).checks["sector_cap"]


def test_gate_liquidity():
    assert not risk_gate.evaluate(base_ctx(entry=0.10)).checks["liquidity"]        # price floor
    assert not risk_gate.evaluate(base_ctx(avg_dollar_vol=None)).checks["liquidity"]  # fail closed
    assert not risk_gate.evaluate(base_ctx(avg_dollar_vol=100000.0)).checks["liquidity"]  # ADV$ floor
    assert not risk_gate.evaluate(base_ctx(avg_dollar_vol=500000.0)).checks["liquidity"]  # participation >1%


def test_gate_halted():
    d = risk_gate.evaluate(base_ctx(halted=True))
    assert not d.checks["not_halted"] and not d.approved


def test_gate_earnings_proximity():
    # unknown earnings date -> FAIL CLOSED
    assert not risk_gate.evaluate(base_ctx(days_to_earnings=None)).checks["earnings_proximity"]
    # inside the 2-day blackout -> fail
    assert not risk_gate.evaluate(base_ctx(days_to_earnings=1)).checks["earnings_proximity"]
    assert not risk_gate.evaluate(base_ctx(days_to_earnings=2)).checks["earnings_proximity"]
    # clear of earnings -> pass
    assert risk_gate.evaluate(base_ctx(days_to_earnings=3)).checks["earnings_proximity"]
    assert not risk_gate.evaluate(base_ctx(days_to_earnings=None)).approved


# ------------------------------------------------------------- chokepoint / bypass
def test_assert_none_raises():
    assert _raises(RiskGateError, risk_gate.assert_trade_allowed, None, symbol="X", qty=10)


def test_assert_unapproved_raises():
    bad = RiskDecision(approved=False, symbol="X", shares=10, reason="nope", checks={})
    assert _raises(RiskGateError, risk_gate.assert_trade_allowed, bad, symbol="X", qty=10)


def test_assert_mismatch_raises():
    ok = RiskDecision(approved=True, symbol="X", shares=10, reason="approved", checks={})
    assert _raises(RiskGateError, risk_gate.assert_trade_allowed, ok, symbol="X", qty=999)
    assert _raises(RiskGateError, risk_gate.assert_trade_allowed, ok, symbol="Y", qty=10)


def test_assert_approved_ok():
    ok = RiskDecision(approved=True, symbol="X", shares=10, reason="approved", checks={})
    risk_gate.assert_trade_allowed(ok, symbol="X", qty=10)      # must not raise


def _real_client(config, *, enabled=False, paper_url="https://paper-api.alpaca.markets"):
    from src.alpaca_client import AlpacaClient
    cfg = dict(config)
    cfg["alpaca"] = dict(config["alpaca"], paper_url=paper_url,
                         enabled=enabled, alpaca_key="PKtest" if enabled else "",
                         alpaca_secret="s" if enabled else "")
    return AlpacaClient(cfg)


def test_submit_requires_decision():
    c = _real_client(make_config(), enabled=True)
    assert _raises(RiskGateError, c.submit_bracket_order, symbol="TEST", qty=100, side="buy",
                   entry_price=3.0, stop_price=2.7, target_price=3.6, account_type="algo",
                   risk_decision=None)


def test_submit_realmoney_account_blocked():
    c = _real_client(make_config(), enabled=True)
    ok = RiskDecision(approved=True, symbol="TEST", shares=100, reason="approved", checks={})
    assert _raises(execution_guard.RealMoneyGuardError, c.submit_bracket_order, symbol="TEST",
                   qty=100, side="buy", entry_price=3.0, stop_price=2.7, target_price=3.6,
                   account_type="agentic", risk_decision=ok)


def test_submit_paperapi_assert_backstops_toctou():
    # Simulate the TOCTOU: gate 1 passed, then paper_url drifted to a non-paper host.
    c = _real_client(make_config(), enabled=True, paper_url="https://api.alpaca.markets")
    c._post = lambda url, body: {"id": "x", "status": "accepted"}          # avoid network
    orig = execution_guard.assert_paper_execution
    execution_guard.assert_paper_execution = lambda **kw: True             # bypass gate 1
    try:
        ok = RiskDecision(approved=True, symbol="TEST", shares=100, reason="approved", checks={})
        assert _raises(AssertionError, c.submit_bracket_order, symbol="TEST", qty=100, side="buy",
                       entry_price=3.0, stop_price=2.7, target_price=3.6, account_type="algo",
                       risk_decision=ok)
    finally:
        execution_guard.assert_paper_execution = orig


def test_submit_happy_path_sends_client_order_id():
    c = _real_client(make_config(), enabled=True)
    captured = {}
    c._post = lambda url, body: captured.update(body) or {"id": "ord1", "status": "accepted"}
    ok = RiskDecision(approved=True, symbol="TEST", shares=100, reason="approved", checks={})
    resp = c.submit_bracket_order(symbol="TEST", qty=100, side="buy", entry_price=3.0,
                                  stop_price=2.7, target_price=3.6, account_type="algo",
                                  risk_decision=ok, client_order_id="algo-TEST-turnaround-2026-07-12")
    assert resp["id"] == "ord1"
    assert captured["client_order_id"] == "algo-TEST-turnaround-2026-07-12"
    assert captured["order_class"] == "bracket"


# ------------------------------------------------------------------- risk state
def test_daily_loss_trip_and_persist():
    db, path = fresh_db()
    try:
        cfg = make_config()
        risk_state.refresh(db, "algo", 100000, cfg)         # sets day baseline + hwm
        assert not risk_state.is_halted(db, "algo")
        risk_state.check_and_trip(db, "algo", 97900, cfg)   # -2.1%
        assert risk_state.is_halted(db, "algo")
        assert db.get_risk_state("algo")["halt_reason"] == "daily_loss"
        # persists across a "restart" (fresh Database over the same file)
        db2 = Database(path)
        assert risk_state.is_halted(db2, "algo")
    finally:
        _rm(path)


def test_drawdown_trip():
    db, path = fresh_db()
    try:
        cfg = make_config()
        risk_state.refresh(db, "algo", 100000, cfg)
        risk_state.check_and_trip(db, "algo", 89000, cfg)   # -11% vs hwm
        assert risk_state.is_halted(db, "algo")
        assert db.get_risk_state("algo")["halt_reason"] == "drawdown"
    finally:
        _rm(path)


def test_daily_loss_clears_next_day_but_drawdown_persists():
    db, path = fresh_db()
    try:
        cfg = make_config()
        # daily-loss halt, then force a stale day_key and refresh -> should clear
        risk_state.refresh(db, "algo", 100000, cfg)
        risk_state.check_and_trip(db, "algo", 97000, cfg)
        assert risk_state.is_halted(db, "algo")
        db.upsert_risk_state("algo", day_key="2000-01-01")   # pretend it's a new day now
        risk_state.refresh(db, "algo", 99000, cfg)           # new-day roll clears daily_loss
        assert not risk_state.is_halted(db, "algo")
        # drawdown halt must NOT clear on a day roll
        risk_state.trip(db, "algo", "drawdown")
        db.upsert_risk_state("algo", day_key="2000-01-01")
        risk_state.refresh(db, "algo", 99000, cfg)
        assert risk_state.is_halted(db, "algo")
    finally:
        _rm(path)


def test_no_equity_no_trip():
    db, path = fresh_db()
    try:
        cfg = make_config()
        risk_state.refresh(db, "algo", 100000, cfg)
        risk_state.check_and_trip(db, "algo", None, cfg)     # broker read failed
        assert not risk_state.is_halted(db, "algo")
    finally:
        _rm(path)


# ------------------------------------------------------------------ fill parsing
def test_parse_submission():
    ok = fill_recorder.parse_submission({"id": "o1", "status": "accepted", "client_order_id": "c1"})
    assert ok["was_rejected"] == 0 and ok["broker_order_id"] == "o1"
    err = fill_recorder.parse_submission({"error": "422 bad", "status_code": 422})
    assert err["was_rejected"] == 1
    assert fill_recorder.parse_submission(None)["was_rejected"] == 1


def test_parse_fill_full_and_partial():
    order = {"status": "filled", "filled_qty": "100", "filled_avg_price": "3.03",
             "submitted_at": "2026-07-12T14:30:00Z", "filled_at": "2026-07-12T14:30:02Z"}
    f = fill_recorder.parse_fill(order, planned_entry=3.00, requested_qty=100,
                                 submitted_at="2026-07-12T14:30:00Z")
    assert f["fill_price"] == 3.03 and f["is_real"] == 1 and f["partial_fill"] == 0
    assert f["slippage_bps"] == 100.0                       # +3c on $3 = +100 bps
    assert f["time_to_fill"] == 2.0
    part = fill_recorder.parse_fill({"status": "partially_filled", "filled_qty": "60",
                                     "filled_avg_price": "3.01"},
                                    planned_entry=3.00, requested_qty=100, submitted_at=None)
    assert part["partial_fill"] == 1


def test_parse_fill_not_filled_yet():
    f = fill_recorder.parse_fill({"status": "new", "filled_qty": "0"},
                                 planned_entry=3.0, requested_qty=100, submitted_at=None)
    assert "fill_price" not in f and f["was_rejected"] == 0


def test_gap_through_stop():
    long_gap = fill_recorder.parse_exit_fill({"filled_avg_price": "2.60"}, planned_exit=2.70,
                                             stop_price=2.70, direction="long")
    assert long_gap["gap_through_stop"] == 1
    long_ok = fill_recorder.parse_exit_fill({"filled_avg_price": "2.71"}, planned_exit=2.70,
                                            stop_price=2.70, direction="long")
    assert long_ok["gap_through_stop"] == 0
    short_gap = fill_recorder.parse_exit_fill({"filled_avg_price": "3.40"}, planned_exit=3.30,
                                              stop_price=3.30, direction="short")
    assert short_gap["gap_through_stop"] == 1


# --------------------------------------------------------------- order executor
def _candidate(symbol="AAA", sector="Technology", lane="turnaround"):
    return {"symbol": symbol, "entry": 3.0, "stop": 2.7, "target": 3.6, "sector": sector,
            "lane": lane, "quality": 8.0, "avg_dollar_vol": 5_000_000.0, "direction": "long",
            "days_to_earnings": 10}


def test_executor_halted_refuses_batch():
    db, path = fresh_db()
    try:
        cfg = make_config()
        risk_state.trip(db, "algo", "drawdown")
        alp = FakeAlpaca(100000, cfg)
        rm = RiskManager(cfg)
        out = order_executor.execute_candidates(db, alp, rm, cfg, [_candidate()])
        assert out.get("halted") and out["placed"] == 0 and out["refused"] == 1
        assert alp.placed == []
    finally:
        _rm(path)


def test_executor_no_equity_refuses_batch():
    db, path = fresh_db()
    try:
        cfg = make_config()
        alp = FakeAlpaca(None, cfg)                          # equity read fails
        out = order_executor.execute_candidates(db, alp, RiskManager(cfg), cfg, [_candidate()])
        assert out.get("no_equity") and out["placed"] == 0
        assert alp.placed == []
    finally:
        _rm(path)


def test_executor_places_records_and_dedupes():
    db, path = fresh_db()
    try:
        cfg = make_config()
        alp = FakeAlpaca(100000, cfg)
        rm = RiskManager(cfg)
        out = order_executor.execute_candidates(db, alp, rm, cfg, [_candidate("AAA")])
        assert out["placed"] == 1, out
        row = db.get_open_algo_trades("algo")[0]
        assert row["is_real"] == 1 and row["broker_order_id"] == "ord-AAA"
        assert row["client_order_id"].startswith("algo-AAA-turnaround-")
        # same symbol+lane+day again -> idempotency refuses (no duplicate real order)
        out2 = order_executor.execute_candidates(db, alp, rm, cfg, [_candidate("AAA")])
        assert out2["refused"] == 1 and out2["placed"] == 0
        assert alp.placed == ["AAA"]                         # only one real submit ever
    finally:
        _rm(path)


def test_executor_within_batch_sector_cap():
    db, path = fresh_db()
    try:
        cfg = make_config()
        cfg["risk"]["max_positions_per_sector"] = 1          # tight, to prove within-batch
        alp = FakeAlpaca(100000, cfg)
        rm = RiskManager(cfg)
        cands = [_candidate("AAA", sector="Energy"), _candidate("BBB", sector="Energy")]
        out = order_executor.execute_candidates(db, alp, rm, cfg, cands)
        assert out["placed"] == 1 and out["refused"] == 1, out   # 2nd blocked by sector cap
        assert alp.placed == ["AAA"]
    finally:
        _rm(path)


def test_executor_reconcile_open_fills():
    db, path = fresh_db()
    try:
        cfg = make_config()
        fills = {"ord-AAA": {"id": "ord-AAA", "status": "filled", "filled_qty": "300",
                             "filled_avg_price": "3.02", "submitted_at": "2026-07-12T14:30:00Z",
                             "filled_at": "2026-07-12T14:30:01Z"}}
        alp = FakeAlpaca(100000, cfg, fills=fills)
        rm = RiskManager(cfg)
        order_executor.execute_candidates(db, alp, rm, cfg, [_candidate("AAA")])
        n = order_executor.reconcile_open_fills(db, alp)
        assert n == 1
        row = db.get_open_algo_trades("algo")[0]
        assert row["fill_price"] == 3.02 and row["filled_qty"] == 300.0
    finally:
        _rm(path)


# ------------------------------------------------------------------ sim vs real
def test_sim_vs_real_view():
    db, path = fresh_db()
    try:
        tid = db.insert_algo_trade({"symbol": "ZZZ", "account_type": "algo", "entry_price": 3.0,
                                    "stop_loss": 2.7, "target_price": 3.6, "shares": 100,
                                    "is_real": 1, "lane": "turnaround", "sector_name": "Tech"})
        db.record_open_fill(tid, fill_price=3.02, slippage_bps=66.7)
        db.record_exit_fill(tid, real_pnl_usd=58.0, real_r_multiple=1.9)
        rows = db.get_sim_vs_real(30)
        assert len(rows) == 1
        assert rows[0]["real_entry"] == 3.02 and rows[0]["real_pnl_usd"] == 58.0
        assert rows[0]["sim_entry"] == 3.0                  # sim number preserved beside real
    finally:
        _rm(path)


def _rm(path):
    try:
        os.remove(path)
    except OSError:
        pass


# --------------------------------------------------------------------- runner
def _run_all():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed, failed = 0, 0
    for t in tests:
        try:
            t()
            print(f"  [PASS] {t.__name__}")
            passed += 1
        except Exception as exc:
            print(f"  [FAIL] {t.__name__}: {type(exc).__name__}: {exc}")
            failed += 1
    print("=" * 60)
    print(f"{passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if _run_all() else 1)
