"""
The paper-vs-real execution wall.

The autonomous scheduler places orders with NO human approval. This module is
the single hard boundary that guarantees an autonomous order can ONLY ever hit
the Alpaca PAPER account, and can ONLY ever be for a paper book -- never the
real-money agentic ($150) or personal accounts, which stay manual-approval via
the existing Robinhood dry-run path and never touch this code.

Design: FAIL CLOSED. `assert_paper_execution()` must be called immediately
before any autonomous order is submitted. If ANYTHING is off -- wrong account,
wrong endpoint host, the global paper_only flag disabled, a malformed URL --
it raises RealMoneyGuardError and the caller must not send the order. There is
no "allow on doubt" path.

Four independent checks, all must pass:
  1. config.alpaca.paper_only is on (defaults on if unset).
  2. account_type is NOT one of the real-money books (hard denylist).
  3. account_type IS on the explicit auto-execute allowlist (paper books only).
  4. the target endpoint host is the Alpaca PAPER host, never the live host.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

# Hard denylist: these are real money and can NEVER be auto-executed here.
REAL_MONEY_ACCOUNTS = frozenset({"agentic", "personal"})

# Alpaca hosts -- the live host is explicitly rejected; only paper is allowed.
LIVE_ALPACA_HOSTS = frozenset({"api.alpaca.markets"})
PAPER_ALPACA_HOSTS = frozenset({"paper-api.alpaca.markets"})


class RealMoneyGuardError(RuntimeError):
    """Raised when an autonomous order would (or might) touch real money.
    The caller MUST abort the order when this is raised."""


def paper_execute_accounts(config: dict[str, Any]) -> frozenset[str]:
    """The books the scheduler is allowed to auto-execute, with any real-money
    account defensively stripped out even if it was mis-listed in config."""
    accts = (config.get("autonomous") or {}).get("auto_execute_accounts", ["algo"])
    return frozenset(a for a in accts if a not in REAL_MONEY_ACCOUNTS)


def assert_paper_execution(*, account_type: str, endpoint_url: str,
                           config: dict[str, Any]) -> bool:
    """Gate an autonomous order. Returns True only if every check passes;
    otherwise raises RealMoneyGuardError (fail closed)."""
    # 1. global paper-only switch (missing => treated as ON, the safe default)
    if not (config.get("alpaca") or {}).get("paper_only", True):
        raise RealMoneyGuardError(
            "alpaca.paper_only is disabled -- autonomous execution refused")

    # 2. never a real-money book
    if account_type in REAL_MONEY_ACCOUNTS:
        raise RealMoneyGuardError(
            f"account '{account_type}' is real-money -- auto-execution forbidden")

    # 3. must be on the explicit paper allowlist
    allowed = paper_execute_accounts(config)
    if account_type not in allowed:
        raise RealMoneyGuardError(
            f"account '{account_type}' is not on the auto-execute allowlist "
            f"{sorted(allowed)} -- refused")

    # 4. endpoint must be the Alpaca PAPER host, never the live host
    host = (urlparse(endpoint_url).hostname or "").lower()
    if host in LIVE_ALPACA_HOSTS:
        raise RealMoneyGuardError(
            f"endpoint host '{host}' is the LIVE Alpaca host -- refused")
    if host not in PAPER_ALPACA_HOSTS:
        raise RealMoneyGuardError(
            f"endpoint host '{host}' is not the Alpaca paper host -- refused")

    return True
