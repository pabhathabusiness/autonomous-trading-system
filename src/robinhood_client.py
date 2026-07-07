"""
Wrapper around the unofficial `robin_stocks` library for Robinhood.

Safety model (see project decision): this system never places a live
order on its own. The scan/analysis pipeline (market_analyzer ->
sector_analyzer -> screener -> technical_analyzer -> proposal_generator)
only ever writes proposals to the database with status='pending'. The
*only* code path that can reach `place_market_order` is a human clicking
"Approve" in the dashboard (or calling the equivalent API endpoint),
which passes confirm=True. Additionally, config["robinhood"]["dry_run"]
(default True) simulates orders without touching the live API at all,
independent of the confirm flag.

If no credentials are configured, the client runs in a read-only
"offline" mode backed by yfinance, so the rest of the system (regime,
sectors, screening, technical analysis, proposals) still works without
a brokerage login.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Optional

import yfinance as yf
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

try:
    import robin_stocks.robinhood as r
except ImportError:  # pragma: no cover - optional at import time
    r = None


class RobinhoodClient:
    def __init__(self, config: dict[str, Any]):
        rh_cfg = config.get("robinhood", {})
        self.enabled = rh_cfg.get("enabled", False)
        self.dry_run = rh_cfg.get("dry_run", True)
        self.authenticated = False

        if self.enabled and r is not None:
            self._login()
        else:
            if self.enabled and r is None:
                logger.warning("robin_stocks not installed; falling back to offline/yfinance mode")
            else:
                logger.info("Robinhood integration disabled in config; running in offline/yfinance mode")

    # ------------------------------------------------------------------ auth
    def _login(self) -> None:
        username = os.environ.get("ROBINHOOD_USERNAME")
        password = os.environ.get("ROBINHOOD_PASSWORD")
        totp_secret = os.environ.get("ROBINHOOD_TOTP_SECRET")

        if not username or not password:
            logger.warning("ROBINHOOD_USERNAME/PASSWORD not set; running in offline/yfinance mode")
            return

        mfa_code = None
        if totp_secret:
            import pyotp
            mfa_code = pyotp.TOTP(totp_secret).now()

        try:
            r.login(username=username, password=password, mfa_code=mfa_code, store_session=True)
            self.authenticated = True
            logger.info("Authenticated with Robinhood as %s", username)
        except Exception as exc:
            logger.error("Robinhood login failed, falling back to offline mode: %s", exc)
            self.authenticated = False

    def logout(self) -> None:
        if self.authenticated and r is not None:
            r.logout()
            self.authenticated = False

    # ---------------------------------------------------------------- quotes
    def get_quote(self, symbol: str) -> Optional[dict[str, Any]]:
        if self.authenticated:
            try:
                quote = r.stocks.get_latest_price(symbol, includeExtendedHours=True)
                price = float(quote[0]) if quote and quote[0] else None
                if price is not None:
                    return {"symbol": symbol, "price": price, "source": "robinhood"}
            except Exception as exc:
                logger.warning("Robinhood quote failed for %s, falling back to yfinance: %s", symbol, exc)

        try:
            fast = yf.Ticker(symbol).fast_info
            price = fast.get("lastPrice") or fast.get("last_price")
            if price is None:
                return None
            return {"symbol": symbol, "price": float(price), "source": "yfinance"}
        except Exception as exc:
            logger.warning("yfinance quote failed for %s: %s", symbol, exc)
            return None

    # ------------------------------------------------------------- accounts
    def get_account_info(self) -> Optional[dict[str, Any]]:
        if not self.authenticated:
            return None
        try:
            profile = r.profiles.load_account_profile()
            return {
                "buying_power": float(profile.get("buying_power", 0)),
                "cash": float(profile.get("cash", 0)),
                "portfolio_cash": float(profile.get("portfolio_cash", 0)) if profile.get("portfolio_cash") else None,
            }
        except Exception as exc:
            logger.error("Failed to fetch Robinhood account info: %s", exc)
            return None

    def get_positions(self) -> list[dict[str, Any]]:
        if not self.authenticated:
            return []
        try:
            holdings = r.account.build_holdings()
            return [
                {
                    "symbol": symbol,
                    "quantity": float(data["quantity"]),
                    "avg_price": float(data["average_buy_price"]),
                    "current_price": float(data["price"]),
                    "market_value": float(data["equity"]),
                }
                for symbol, data in holdings.items()
            ]
        except Exception as exc:
            logger.error("Failed to fetch Robinhood positions: %s", exc)
            return []

    # ---------------------------------------------------------------- orders
    def place_market_order(
        self,
        symbol: str,
        quantity: float,
        side: str,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """Places (or simulates) a market order.

        `confirm=True` must be passed explicitly by the caller -- this is
        the human-in-the-loop gate. This method must only ever be invoked
        from an explicit user action (dashboard "Approve" click or its API
        equivalent), never from the automated scan/proposal pipeline.
        """
        if not confirm:
            raise ValueError("place_market_order requires explicit confirm=True (human approval gate)")
        if side not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")

        if self.dry_run or not self.authenticated:
            order_id = f"DRYRUN-{uuid.uuid4().hex[:10]}"
            logger.info(
                "[DRY RUN] Would %s %s shares of %s (authenticated=%s)",
                side, quantity, symbol, self.authenticated,
            )
            return {"order_id": order_id, "status": "simulated", "symbol": symbol,
                     "quantity": quantity, "side": side}

        try:
            if side == "buy":
                result = r.orders.order_buy_market(symbol, quantity)
            else:
                result = r.orders.order_sell_market(symbol, quantity)
            order_id = result.get("id", f"UNKNOWN-{uuid.uuid4().hex[:10]}")
            logger.info("LIVE order placed: %s %s %s -> order_id=%s", side, quantity, symbol, order_id)
            return {"order_id": order_id, "status": "submitted", "symbol": symbol,
                     "quantity": quantity, "side": side, "raw": result}
        except Exception as exc:
            logger.error("Live order failed for %s: %s", symbol, exc)
            return {"order_id": None, "status": "failed", "error": str(exc)}

    def cancel_order(self, order_id: str) -> bool:
        if not self.authenticated or order_id.startswith("DRYRUN"):
            logger.info("[DRY RUN] Would cancel order %s", order_id)
            return True
        try:
            r.orders.cancel_stock_order(order_id)
            return True
        except Exception as exc:
            logger.error("Failed to cancel order %s: %s", order_id, exc)
            return False
