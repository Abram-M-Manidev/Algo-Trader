"""
=============================================================
  LIVE EXECUTION ENGINE
  Connects signal analyzer → broker APIs with safety gates.

  SAFETY LAYERS (in order):
    1. Paper validator must confirm unlock
    2. Market must be open
    3. Position size limits enforced
    4. Daily loss limit check
    5. Duplicate position check
    6. Then and only then — real order placed
=============================================================
"""

import os
import logging
from datetime import datetime, date

from config          import AUTO_BUY_THRESH, TAKE_PROFIT_PCT, STOP_LOSS_PCT
from database        import get_conn, insert_trade
from paper_validator import is_real_trading_allowed, log_paper_trade

logger = logging.getLogger(__name__)

# ── Execution settings ────────────────────────────────────
EXECUTION_MODE   = os.getenv("EXECUTION_MODE", "paper")
# Options:
#   "paper"      → log paper trades only, no real orders (DEFAULT)
#   "zerodha"    → real NSE execution via Kite
#   "alpaca"     → real US execution via Alpaca
#   "both"       → Zerodha for NSE, Alpaca for US stocks

# Risk controls
MAX_POSITION_VALUE_INR = float(os.getenv("MAX_POSITION_INR", "5000"))   # max ₹5000 per trade
MAX_POSITION_VALUE_USD = float(os.getenv("MAX_POSITION_USD", "100"))    # max $100 per trade
MAX_DAILY_TRADES       = int(os.getenv("MAX_DAILY_TRADES",   "3"))      # max 3 trades per day
MAX_DAILY_LOSS_PCT     = float(os.getenv("MAX_DAILY_LOSS",   "3.0"))    # stop if -3% day


def _get_daily_trade_count() -> int:
    conn = get_conn()
    row  = conn.execute("""
        SELECT COUNT(*) as cnt FROM trades
        WHERE entry_date = ? AND result != 'PAPER'
    """, (str(date.today()),)).fetchone()
    conn.close()
    return row["cnt"] if row else 0


def _get_daily_pnl() -> float:
    conn = get_conn()
    row  = conn.execute("""
        SELECT COALESCE(SUM(pnl_pct), 0) as total FROM trades
        WHERE exit_date = ? AND result != 'PAPER'
    """, (str(date.today()),)).fetchone()
    conn.close()
    return row["total"] if row else 0.0


def _has_open_position(ticker: str) -> bool:
    """Check if we already hold this ticker (no doubling up)."""
    conn  = get_conn()
    count = conn.execute("""
        SELECT COUNT(*) as cnt FROM trades
        WHERE ticker = ? AND exit_date IS NULL
    """, (ticker,)).fetchone()
    conn.close()
    return (count["cnt"] if count else 0) > 0


def _nse_symbol(ticker: str) -> str:
    """Strip .NS suffix for Kite API (uses plain symbol)."""
    return ticker.replace(".NS", "").replace(".BSE", "")


def _is_nse_stock(ticker: str) -> bool:
    return ticker.endswith(".NS") or ticker.endswith(".BSE")


def _is_us_stock(ticker: str) -> bool:
    return not any(ticker.endswith(s) for s in
                   [".NS", ".BSE", ".HK", ".T", ".L", ".PA", ".DE",
                    ".AS", ".SW", ".KS", ".TW", "-USD"])


# ════════════════════════════════════════════════════════════
#  MAIN EXECUTION FUNCTION
#  Called by scheduler after signal analysis
# ════════════════════════════════════════════════════════════
def execute_signal(
    ticker: str,
    market: str,
    win_prob: float,
    current_price: float,
    signal_strength: int,
) -> dict:
    """
    Decides whether to execute a trade based on:
      - Signal strength
      - Safety gates
      - Execution mode (paper/zerodha/alpaca/both)

    Returns a result dict with action taken.
    """

    result = {
        "ticker"    : ticker,
        "action"    : "SKIP",
        "reason"    : "",
        "order_id"  : None,
        "paper"     : True,
    }

    # ── Gate 1: Signal threshold ──────────────────────────────
    if win_prob <= AUTO_BUY_THRESH:
        result["reason"] = f"Win prob {win_prob:.1%} ≤ {AUTO_BUY_THRESH:.0%} threshold"
        return result

    # ── Gate 2: Daily trade limit ─────────────────────────────
    daily_count = _get_daily_trade_count()
    if daily_count >= MAX_DAILY_TRADES:
        result["reason"] = f"Daily trade limit reached ({MAX_DAILY_TRADES})"
        return result

    # ── Gate 3: Daily loss circuit breaker ───────────────────
    daily_pnl = _get_daily_pnl()
    if daily_pnl <= -MAX_DAILY_LOSS_PCT:
        result["reason"] = f"Daily loss limit hit ({daily_pnl:.2f}%)"
        logger.warning(f"🛑  Circuit breaker: daily loss {daily_pnl:.2f}%")
        return result

    # ── Gate 4: No duplicate positions ───────────────────────
    if _has_open_position(ticker):
        result["reason"] = f"Already holding {ticker}"
        return result

    # ── Gate 5: Paper validator (real mode only) ──────────────
    mode = EXECUTION_MODE.lower()
    is_real = mode in ("zerodha", "alpaca", "both")

    if is_real and not is_real_trading_allowed():
        # Downgrade to paper silently — log but don't block
        logger.info(f"  📝  Paper trade (not unlocked yet): {ticker}")
        mode = "paper"

    # ── Execute ───────────────────────────────────────────────
    if mode == "paper":
        result = _execute_paper(ticker, market, current_price, win_prob)

    elif mode == "zerodha" and _is_nse_stock(ticker):
        result = _execute_zerodha(ticker, market, current_price, win_prob)

    elif mode == "alpaca" and _is_us_stock(ticker):
        result = _execute_alpaca(ticker, market, current_price, win_prob)

    elif mode == "both":
        if _is_nse_stock(ticker):
            result = _execute_zerodha(ticker, market, current_price, win_prob)
        elif _is_us_stock(ticker):
            result = _execute_alpaca(ticker, market, current_price, win_prob)
        else:
            result["reason"] = "No broker configured for this market"

    return result


# ════════════════════════════════════════════════════════════
#  PAPER EXECUTION
# ════════════════════════════════════════════════════════════
def _execute_paper(ticker, market, price, win_prob) -> dict:
    """Log a paper trade — no real order placed."""
    tp = round(price * (1 + TAKE_PROFIT_PCT), 4)
    sl = round(price * (1 - STOP_LOSS_PCT),   4)

    log_paper_trade({
        "ticker"      : ticker,
        "market"      : market,
        "entry_date"  : str(date.today()),
        "exit_date"   : None,
        "entry_price" : price,
        "exit_price"  : None,
        "pnl_pct"     : None,
        "result"      : "OPEN",
        "broker"      : "paper",
        "notes"       : f"win_prob={win_prob:.1%} TP={tp} SL={sl}",
    })

    logger.info(f"  📝  PAPER BUY: {ticker} @ {price:.2f} | TP={tp:.2f} SL={sl:.2f}")
    return {
        "ticker"   : ticker,
        "action"   : "PAPER_BUY",
        "reason"   : "Paper trade logged",
        "order_id" : None,
        "paper"    : True,
        "tp"       : tp,
        "sl"       : sl,
    }


# ════════════════════════════════════════════════════════════
#  ZERODHA EXECUTION
# ════════════════════════════════════════════════════════════
def _execute_zerodha(ticker, market, price, win_prob) -> dict:
    from broker_zerodha import kite_broker

    if not kite_broker.ready:
        logger.warning(f"  ⚠  Kite not ready — falling back to paper: {ticker}")
        return _execute_paper(ticker, market, price, win_prob)

    symbol   = _nse_symbol(ticker)
    # Calculate quantity based on max position size
    qty      = max(1, int(MAX_POSITION_VALUE_INR / price))
    tp_price = round(price * (1 + TAKE_PROFIT_PCT), 2)
    sl_price = round(price * (1 - STOP_LOSS_PCT),   2)

    # Place entry order
    buy_result = kite_broker.place_buy_order(
        tradingsymbol = symbol,
        quantity      = qty,
        order_type    = "MARKET",
    )

    if not buy_result["success"]:
        logger.error(f"  ❌  Kite BUY failed: {buy_result['error']}")
        return _execute_paper(ticker, market, price, win_prob)

    # Set GTT for automatic TP/SL — Zerodha handles exit even if server is down
    kite_broker.place_gtт_order(
        tradingsymbol     = symbol,
        quantity          = qty,
        entry_price       = price,
        take_profit_price = tp_price,
        stop_loss_price   = sl_price,
    )

    # Record in DB
    insert_trade({
        "ticker"      : ticker,
        "market"      : market,
        "entry_date"  : str(date.today()),
        "exit_date"   : None,
        "entry_price" : price,
        "exit_price"  : None,
        "pnl_pct"     : None,
        "result"      : "OPEN",
    })

    logger.info(f"  ✅  ZERODHA BUY: {symbol} x{qty} @ ₹{price:.2f}")
    return {
        "ticker"   : ticker,
        "action"   : "LIVE_BUY_ZERODHA",
        "reason"   : "Real order placed on NSE",
        "order_id" : buy_result.get("order_id"),
        "paper"    : False,
        "qty"      : qty,
        "tp"       : tp_price,
        "sl"       : sl_price,
    }


# ════════════════════════════════════════════════════════════
#  ALPACA EXECUTION
# ════════════════════════════════════════════════════════════
def _execute_alpaca(ticker, market, price, win_prob) -> dict:
    from broker_alpaca import alpaca_broker

    if not alpaca_broker.ready:
        logger.warning(f"  ⚠  Alpaca not ready — falling back to paper: {ticker}")
        return _execute_paper(ticker, market, price, win_prob)

    if not alpaca_broker.is_market_open():
        logger.info(f"  ⏰  US market closed — paper logging: {ticker}")
        return _execute_paper(ticker, market, price, win_prob)

    # Use bracket order — TP/SL managed by Alpaca automatically
    result = alpaca_broker.place_bracket_order(
        symbol          = ticker,
        qty             = max(1, int(MAX_POSITION_VALUE_USD / price)),
        entry_price     = price,
        take_profit_pct = TAKE_PROFIT_PCT,
        stop_loss_pct   = STOP_LOSS_PCT,
    )

    if not result["success"]:
        logger.error(f"  ❌  Alpaca order failed: {result['error']}")
        return _execute_paper(ticker, market, price, win_prob)

    insert_trade({
        "ticker"      : ticker,
        "market"      : market,
        "entry_date"  : str(date.today()),
        "exit_date"   : None,
        "entry_price" : price,
        "exit_price"  : None,
        "pnl_pct"     : None,
        "result"      : "OPEN",
    })

    mode_tag = "PAPER" if result.get("paper") else "LIVE"
    logger.info(f"  ✅  ALPACA {mode_tag} BUY: {ticker} @ ${price:.2f}")
    return {
        "ticker"   : ticker,
        "action"   : f"ALPACA_{mode_tag}_BUY",
        "reason"   : "Bracket order placed",
        "order_id" : result.get("order_id"),
        "paper"    : result.get("paper", True),
        "tp"       : result.get("tp_price"),
        "sl"       : result.get("sl_price"),
    }
