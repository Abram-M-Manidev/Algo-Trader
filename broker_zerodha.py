"""
=============================================================
  ZERODHA KITE BROKER  — Real NSE Execution
  Docs: https://kite.trade/docs/connect/v3/
  Cost: ₹2000 one-time for API access at zerodha.com/developer
=============================================================

SETUP STEPS:
  1. Open Zerodha account at zerodha.com (free)
  2. Buy Kite Connect API access at kite.trade (₹2000/year)
  3. Create an app at developers.kite.trade
  4. Copy your api_key and api_secret into env vars
  5. Run generate_access_token() once per day (Zerodha requires daily login)

HOW DAILY AUTH WORKS:
  Zerodha access tokens expire every day at 6 AM.
  The system auto-generates a new one using your saved credentials.
  First time: you must do it manually (browser login).
  After that: automated via request_token flow.
"""

import os
import json
import logging
from datetime import datetime, date

logger = logging.getLogger(__name__)

# Kite Connect SDK — install with: pip install kiteconnect
try:
    from kiteconnect import KiteConnect
    KITE_AVAILABLE = True
except ImportError:
    KITE_AVAILABLE = False
    logger.warning("kiteconnect not installed. Run: pip install kiteconnect")

# ── Credentials (set in Render env vars) ─────────────────
KITE_API_KEY     = os.getenv("KITE_API_KEY",     "")
KITE_API_SECRET  = os.getenv("KITE_API_SECRET",  "")
KITE_ACCESS_TOKEN_FILE = "data/kite_token.json"


class ZerodhaKiteBroker:
    """
    Wraps Kite Connect for order placement.
    All methods return a dict with keys: success, data, error
    """

    def __init__(self):
        self.kite   = None
        self.ready  = False

        if not KITE_AVAILABLE:
            logger.error("kiteconnect package not installed.")
            return
        if not KITE_API_KEY:
            logger.error("KITE_API_KEY not set in environment.")
            return

        self.kite  = KiteConnect(api_key=KITE_API_KEY)
        self._load_token()

    # ── Token management ─────────────────────────────────────

    def _load_token(self):
        """Load saved access token from disk (valid until 6 AM next day)."""
        try:
            if not os.path.exists(KITE_ACCESS_TOKEN_FILE):
                logger.warning("No saved Kite token. Call get_login_url() to authenticate.")
                return

            with open(KITE_ACCESS_TOKEN_FILE) as f:
                data = json.load(f)

            saved_date = data.get("date")
            token      = data.get("access_token")

            if saved_date != str(date.today()):
                logger.warning("Kite token expired (new day). Re-authenticate.")
                return

            self.kite.set_access_token(token)
            self.ready = True
            logger.info("✅  Kite token loaded — broker ready.")

        except Exception as e:
            logger.error(f"Token load error: {e}")

    def get_login_url(self) -> str:
        """
        Step 1 of auth: get the URL the user must visit once per day.
        Returns a URL string.
        """
        if not self.kite:
            return ""
        return self.kite.login_url()

    def generate_access_token(self, request_token: str) -> dict:
        """
        Step 2 of auth: exchange request_token for access_token.
        Call this once after user visits login URL and you get request_token.
        """
        try:
            session = self.kite.generate_session(
                request_token, api_secret=KITE_API_SECRET
            )
            access_token = session["access_token"]
            self.kite.set_access_token(access_token)

            # Save token with today's date
            os.makedirs("data", exist_ok=True)
            with open(KITE_ACCESS_TOKEN_FILE, "w") as f:
                json.dump({
                    "access_token": access_token,
                    "date": str(date.today()),
                }, f)

            self.ready = True
            logger.info("✅  Kite access token generated and saved.")
            return {"success": True, "data": access_token}

        except Exception as e:
            logger.error(f"Token generation failed: {e}")
            return {"success": False, "error": str(e)}

    # ── Market data ───────────────────────────────────────────

    def get_quote(self, tradingsymbol: str, exchange: str = "NSE") -> dict:
        """Get live quote for a symbol."""
        if not self.ready:
            return {"success": False, "error": "Broker not ready"}
        try:
            instrument = f"{exchange}:{tradingsymbol}"
            quote = self.kite.quote([instrument])
            return {"success": True, "data": quote[instrument]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_holdings(self) -> dict:
        """Get current portfolio holdings."""
        if not self.ready:
            return {"success": False, "error": "Broker not ready"}
        try:
            return {"success": True, "data": self.kite.holdings()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_positions(self) -> dict:
        """Get open positions."""
        if not self.ready:
            return {"success": False, "error": "Broker not ready"}
        try:
            return {"success": True, "data": self.kite.positions()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_funds(self) -> dict:
        """Get available margin/funds."""
        if not self.ready:
            return {"success": False, "error": "Broker not ready"}
        try:
            return {"success": True, "data": self.kite.margins()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Order placement ───────────────────────────────────────

    def place_buy_order(
        self,
        tradingsymbol: str,
        quantity: int,
        exchange: str = "NSE",
        order_type: str = "MARKET",
        price: float = 0.0,
    ) -> dict:
        """
        Place a real BUY order on NSE.

        Args:
            tradingsymbol: e.g. "RELIANCE", "TCS", "INFY"
            quantity:      number of shares
            exchange:      "NSE" or "BSE"
            order_type:    "MARKET" or "LIMIT"
            price:         required only for LIMIT orders
        """
        if not self.ready:
            return {"success": False, "error": "Broker not ready — authenticate first"}

        try:
            params = dict(
                tradingsymbol = tradingsymbol,
                exchange      = exchange,
                transaction_type = self.kite.TRANSACTION_TYPE_BUY,
                quantity      = quantity,
                order_type    = (self.kite.ORDER_TYPE_MARKET
                                 if order_type == "MARKET"
                                 else self.kite.ORDER_TYPE_LIMIT),
                product       = self.kite.PRODUCT_CNC,   # delivery/equity
                validity      = self.kite.VALIDITY_DAY,
            )
            if order_type == "LIMIT":
                params["price"] = price

            order_id = self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                **params
            )

            logger.info(f"✅  BUY order placed: {tradingsymbol} x{quantity} → order_id={order_id}")
            return {"success": True, "order_id": order_id, "data": params}

        except Exception as e:
            logger.error(f"BUY order failed [{tradingsymbol}]: {e}")
            return {"success": False, "error": str(e)}

    def place_sell_order(
        self,
        tradingsymbol: str,
        quantity: int,
        exchange: str = "NSE",
        order_type: str = "MARKET",
        price: float = 0.0,
    ) -> dict:
        """Place a real SELL order on NSE."""
        if not self.ready:
            return {"success": False, "error": "Broker not ready — authenticate first"}

        try:
            params = dict(
                tradingsymbol    = tradingsymbol,
                exchange         = exchange,
                transaction_type = self.kite.TRANSACTION_TYPE_SELL,
                quantity         = quantity,
                order_type       = (self.kite.ORDER_TYPE_MARKET
                                    if order_type == "MARKET"
                                    else self.kite.ORDER_TYPE_LIMIT),
                product          = self.kite.PRODUCT_CNC,
                validity         = self.kite.VALIDITY_DAY,
            )
            if order_type == "LIMIT":
                params["price"] = price

            order_id = self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                **params
            )

            logger.info(f"✅  SELL order placed: {tradingsymbol} x{quantity} → order_id={order_id}")
            return {"success": True, "order_id": order_id, "data": params}

        except Exception as e:
            logger.error(f"SELL order failed [{tradingsymbol}]: {e}")
            return {"success": False, "error": str(e)}

    def place_gtт_order(
        self,
        tradingsymbol: str,
        quantity: int,
        entry_price: float,
        take_profit_price: float,
        stop_loss_price: float,
        exchange: str = "NSE",
    ) -> dict:
        """
        Place a GTT (Good Till Triggered) order — Zerodha's built-in
        TP/SL bracket. Once placed, Zerodha monitors and executes
        automatically without your server needing to run.

        This is the SAFEST way to run automated trades.
        """
        if not self.ready:
            return {"success": False, "error": "Broker not ready"}

        try:
            # GTT for take profit (single trigger)
            tp_gtt = self.kite.place_gtt(
                trigger_type  = self.kite.GTT_TYPE_SINGLE,
                tradingsymbol = tradingsymbol,
                exchange      = exchange,
                trigger_values= [take_profit_price],
                last_price    = entry_price,
                orders=[{
                    "exchange"        : exchange,
                    "tradingsymbol"   : tradingsymbol,
                    "transaction_type": self.kite.TRANSACTION_TYPE_SELL,
                    "quantity"        : quantity,
                    "order_type"      : self.kite.ORDER_TYPE_LIMIT,
                    "product"         : self.kite.PRODUCT_CNC,
                    "price"           : take_profit_price,
                }]
            )

            # GTT for stop loss (single trigger)
            sl_gtt = self.kite.place_gtt(
                trigger_type  = self.kite.GTT_TYPE_SINGLE,
                tradingsymbol = tradingsymbol,
                exchange      = exchange,
                trigger_values= [stop_loss_price],
                last_price    = entry_price,
                orders=[{
                    "exchange"        : exchange,
                    "tradingsymbol"   : tradingsymbol,
                    "transaction_type": self.kite.TRANSACTION_TYPE_SELL,
                    "quantity"        : quantity,
                    "order_type"      : self.kite.ORDER_TYPE_LIMIT,
                    "product"         : self.kite.PRODUCT_CNC,
                    "price"           : stop_loss_price,
                }]
            )

            logger.info(f"✅  GTT orders set: TP={take_profit_price} SL={stop_loss_price}")
            return {
                "success": True,
                "tp_gtt_id": tp_gtt,
                "sl_gtt_id": sl_gtt,
            }

        except Exception as e:
            logger.error(f"GTT order failed: {e}")
            return {"success": False, "error": str(e)}

    def get_order_history(self) -> dict:
        """Get today's order history."""
        if not self.ready:
            return {"success": False, "error": "Broker not ready"}
        try:
            return {"success": True, "data": self.kite.orders()}
        except Exception as e:
            return {"success": False, "error": str(e)}


# Singleton — import and use anywhere
kite_broker = ZerodhaKiteBroker()
