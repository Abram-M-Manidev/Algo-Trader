"""
=============================================================
  ALPACA BROKER  — Real + Paper US Stock Execution
  Docs: https://alpaca.markets/docs/
  Cost: COMPLETELY FREE (including API access)

SETUP STEPS:
  1. Create free account at alpaca.markets
  2. Go to Paper Trading → get API Key + Secret
  3. Test with paper trading for 1-2 months
  4. When ready: go to Live Trading → get new keys
  5. Set ALPACA_PAPER=false in env vars to go live
=============================================================
"""

import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Alpaca SDK — install with: pip install alpaca-trade-api
try:
    import alpaca_trade_api as tradeapi
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False
    logger.warning("alpaca-trade-api not installed. Run: pip install alpaca-trade-api")

# ── Credentials ───────────────────────────────────────────
ALPACA_API_KEY    = os.getenv("ALPACA_API_KEY",    "")
ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET", "")
ALPACA_PAPER      = os.getenv("ALPACA_PAPER",      "true").lower() == "true"

# Alpaca endpoints
PAPER_URL = "https://paper-api.alpaca.markets"
LIVE_URL  = "https://api.alpaca.markets"


class AlpacaBroker:
    """
    Wraps Alpaca Trade API for US stock order placement.
    Defaults to PAPER trading (safe) until you change ALPACA_PAPER=false.
    """

    def __init__(self):
        self.api   = None
        self.ready = False
        self.paper = ALPACA_PAPER

        if not ALPACA_AVAILABLE:
            logger.error("alpaca-trade-api not installed.")
            return
        if not ALPACA_API_KEY:
            logger.error("ALPACA_API_KEY not set.")
            return

        base_url = PAPER_URL if ALPACA_PAPER else LIVE_URL
        mode_tag = "PAPER" if ALPACA_PAPER else "🔴 LIVE"

        try:
            self.api = tradeapi.REST(
                ALPACA_API_KEY,
                ALPACA_API_SECRET,
                base_url,
                api_version="v2"
            )
            # Test connection
            account = self.api.get_account()
            self.ready = True
            logger.info(
                f"✅  Alpaca {mode_tag} ready — "
                f"Buying power: ${float(account.buying_power):,.2f}"
            )
        except Exception as e:
            logger.error(f"Alpaca connection failed: {e}")

    # ── Account info ──────────────────────────────────────────

    def get_account(self) -> dict:
        if not self.ready:
            return {"success": False, "error": "Alpaca not ready"}
        try:
            acc = self.api.get_account()
            return {
                "success": True,
                "data": {
                    "cash":          float(acc.cash),
                    "buying_power":  float(acc.buying_power),
                    "portfolio_value": float(acc.portfolio_value),
                    "equity":        float(acc.equity),
                    "paper":         self.paper,
                    "status":        acc.status,
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_positions(self) -> dict:
        if not self.ready:
            return {"success": False, "error": "Alpaca not ready"}
        try:
            positions = self.api.list_positions()
            return {
                "success": True,
                "data": [{
                    "symbol":     p.symbol,
                    "qty":        int(p.qty),
                    "avg_entry":  float(p.avg_entry_price),
                    "current":    float(p.current_price),
                    "pnl":        float(p.unrealized_pl),
                    "pnl_pct":    float(p.unrealized_plpc) * 100,
                } for p in positions]
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_portfolio_history(self) -> dict:
        if not self.ready:
            return {"success": False, "error": "Alpaca not ready"}
        try:
            hist = self.api.get_portfolio_history(period="1M", timeframe="1D")
            return {
                "success": True,
                "data": {
                    "equity":     hist.equity,
                    "timestamps": hist.timestamp,
                    "pnl":        hist.profit_loss,
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def is_market_open(self) -> bool:
        """Check if US market is currently open."""
        if not self.ready:
            return False
        try:
            clock = self.api.get_clock()
            return clock.is_open
        except:
            return False

    def get_quote(self, symbol: str) -> dict:
        """Get latest quote for a US stock."""
        if not self.ready:
            return {"success": False, "error": "Alpaca not ready"}
        try:
            quote = self.api.get_latest_quote(symbol)
            return {
                "success": True,
                "data": {
                    "symbol":    symbol,
                    "ask":       float(quote.ap),
                    "bid":       float(quote.bp),
                    "timestamp": str(quote.t),
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Order placement ───────────────────────────────────────

    def place_buy_order(
        self,
        symbol: str,
        qty: int = None,
        notional: float = None,   # buy $X worth instead of qty shares
        order_type: str = "market",
        limit_price: float = None,
        time_in_force: str = "day",
    ) -> dict:
        """
        Place a BUY order.

        Args:
            symbol:       e.g. "AAPL", "NVDA", "TSLA"
            qty:          number of shares (use this OR notional)
            notional:     dollar amount to buy e.g. 100.0 = buy $100 of stock
            order_type:   "market" or "limit"
            limit_price:  required for limit orders
            time_in_force: "day" or "gtc" (good till cancelled)
        """
        if not self.ready:
            return {"success": False, "error": "Alpaca not ready"}
        if not self.is_market_open():
            return {"success": False, "error": "US market is currently closed"}

        try:
            params = dict(
                symbol         = symbol,
                side           = "buy",
                type           = order_type,
                time_in_force  = time_in_force,
            )
            if notional:
                params["notional"] = str(round(notional, 2))
            else:
                params["qty"] = str(qty)

            if order_type == "limit":
                params["limit_price"] = str(limit_price)

            order = self.api.submit_order(**params)
            logger.info(f"✅  Alpaca BUY: {symbol} → order_id={order.id}")
            return {
                "success":  True,
                "order_id": order.id,
                "status":   order.status,
                "symbol":   symbol,
                "paper":    self.paper,
            }

        except Exception as e:
            logger.error(f"Alpaca BUY failed [{symbol}]: {e}")
            return {"success": False, "error": str(e)}

    def place_sell_order(
        self,
        symbol: str,
        qty: int = None,
        order_type: str = "market",
        limit_price: float = None,
    ) -> dict:
        """Place a SELL order."""
        if not self.ready:
            return {"success": False, "error": "Alpaca not ready"}

        try:
            params = dict(
                symbol        = symbol,
                qty           = str(qty),
                side          = "sell",
                type          = order_type,
                time_in_force = "day",
            )
            if order_type == "limit":
                params["limit_price"] = str(limit_price)

            order = self.api.submit_order(**params)
            logger.info(f"✅  Alpaca SELL: {symbol} → order_id={order.id}")
            return {
                "success":  True,
                "order_id": order.id,
                "status":   order.status,
            }

        except Exception as e:
            logger.error(f"Alpaca SELL failed [{symbol}]: {e}")
            return {"success": False, "error": str(e)}

    def place_bracket_order(
        self,
        symbol: str,
        qty: int,
        entry_price: float,
        take_profit_pct: float = 0.05,
        stop_loss_pct:   float = 0.02,
    ) -> dict:
        """
        Place a bracket order — entry + TP + SL in one shot.
        Alpaca manages TP/SL automatically, even when your server is offline.

        This is the SAFEST way to run automated US stock trades.
        """
        if not self.ready:
            return {"success": False, "error": "Alpaca not ready"}

        tp_price = round(entry_price * (1 + take_profit_pct), 2)
        sl_price = round(entry_price * (1 - stop_loss_pct),   2)

        try:
            order = self.api.submit_order(
                symbol         = symbol,
                qty            = str(qty),
                side           = "buy",
                type           = "market",
                time_in_force  = "day",
                order_class    = "bracket",
                take_profit    = {"limit_price": str(tp_price)},
                stop_loss      = {"stop_price":  str(sl_price)},
            )

            logger.info(
                f"✅  Bracket order: {symbol} x{qty} | "
                f"TP={tp_price} SL={sl_price} | order_id={order.id}"
            )
            return {
                "success":    True,
                "order_id":   order.id,
                "symbol":     symbol,
                "tp_price":   tp_price,
                "sl_price":   sl_price,
                "paper":      self.paper,
            }

        except Exception as e:
            logger.error(f"Bracket order failed [{symbol}]: {e}")
            return {"success": False, "error": str(e)}

    def cancel_all_orders(self) -> dict:
        """Emergency cancel all open orders."""
        if not self.ready:
            return {"success": False, "error": "Alpaca not ready"}
        try:
            self.api.cancel_all_orders()
            logger.warning("⚠  All Alpaca orders cancelled.")
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_orders(self) -> dict:
        if not self.ready:
            return {"success": False, "error": "Alpaca not ready"}
        try:
            orders = self.api.list_orders(status="all", limit=50)
            return {
                "success": True,
                "data": [{
                    "id":        o.id,
                    "symbol":    o.symbol,
                    "side":      o.side,
                    "qty":       o.qty,
                    "status":    o.status,
                    "filled_at": str(o.filled_at),
                    "filled_avg_price": str(o.filled_avg_price),
                } for o in orders]
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


# Singleton
alpaca_broker = AlpacaBroker()
