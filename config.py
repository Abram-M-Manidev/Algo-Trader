"""
=============================================================
  GLOBAL CONFIGURATION
  Edit this file to customize the entire system
=============================================================
"""

# ─────────────────────────────────────────────────────────────
#  STOCK UNIVERSE  — Every major market covered
# ─────────────────────────────────────────────────────────────
WATCHLIST = {
    # ── India NSE ────────────────────────────────────────────
    "NSE": [
        "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS",
        "ICICIBANK.NS", "WIPRO.NS", "SBIN.NS", "BAJFINANCE.NS",
        "ADANIENT.NS", "TATAMOTORS.NS", "MARUTI.NS", "SUNPHARMA.NS",
        "ONGC.NS", "NTPC.NS", "POWERGRID.NS", "LTIM.NS",
        "HCLTECH.NS", "AXISBANK.NS", "KOTAKBANK.NS", "ITC.NS",
    ],
    # ── USA S&P 500 Core ─────────────────────────────────────
    "USA": [
        "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN",
        "META", "TSLA", "BRK-B", "JPM", "V",
        "UNH", "XOM", "JNJ", "WMT", "MA",
        "PG", "HD", "CVX", "MRK", "ABBV",
    ],
    # ── Europe ───────────────────────────────────────────────
    "EU": [
        "ASML.AS", "SAP.DE", "NESN.SW", "NOVN.SW", "ROG.SW",
        "MC.PA", "OR.PA", "SIE.DE", "HSBA.L", "BP.L",
    ],
    # ── Asia Pacific ─────────────────────────────────────────
    "APAC": [
        "9984.T",   # SoftBank
        "7203.T",   # Toyota
        "005930.KS",# Samsung
        "000660.KS",# SK Hynix
        "700.HK",   # Tencent
        "9988.HK",  # Alibaba
        "2317.TW",  # Foxconn
        "2330.TW",  # TSMC
    ],
    # ── Crypto ETFs & Commodities ────────────────────────────
    "MACRO": [
        "GLD",   # Gold ETF
        "SLV",   # Silver ETF
        "USO",   # Oil ETF
        "QQQ",   # NASDAQ ETF
        "SPY",   # S&P500 ETF
        "BTC-USD","ETH-USD",
    ],
}

# Flatten all tickers into one list for easy iteration
ALL_TICKERS = [t for group in WATCHLIST.values() for t in group]

# ─────────────────────────────────────────────────────────────
#  ANALYSIS PARAMETERS
# ─────────────────────────────────────────────────────────────
LOOKBACK_DAYS       = 90        # days of history to analyze
RSI_PERIOD          = 14
MACD_FAST           = 12
MACD_SLOW           = 26
MACD_SIGNAL         = 9
BB_PERIOD           = 20        # Bollinger Bands period
BB_STD              = 2.0       # Bollinger Bands std devs
ADX_PERIOD          = 14        # ADX trend strength period

# ─────────────────────────────────────────────────────────────
#  TRADE RULES
# ─────────────────────────────────────────────────────────────
TAKE_PROFIT_PCT     = 0.05      # +5% take profit
STOP_LOSS_PCT       = 0.02      # -2% stop loss
WIN_BIAS_THRESH     = 0.50      # Bullish bias label
AUTO_BUY_THRESH     = 0.60      # Auto-buy trigger

# ─────────────────────────────────────────────────────────────
#  SCHEDULER
# ─────────────────────────────────────────────────────────────
DAILY_RUN_HOUR      = 18        # Run analysis at 6 PM IST daily
DAILY_RUN_MINUTE    = 30
REPORT_INTERVAL_WEEKS = 3       # Send report every 3 weeks

# ─────────────────────────────────────────────────────────────
#  EMAIL (Gmail SMTP — free)
# ─────────────────────────────────────────────────────────────
import os
EMAIL_SENDER        = os.getenv("EMAIL_SENDER", "your_gmail@gmail.com")
EMAIL_PASSWORD      = os.getenv("EMAIL_PASSWORD", "your_app_password")
EMAIL_RECIPIENT     = os.getenv("EMAIL_RECIPIENT", "your_gmail@gmail.com")
SMTP_HOST           = "smtp.gmail.com"
SMTP_PORT           = 587

# ─────────────────────────────────────────────────────────────
#  DATABASE
# ─────────────────────────────────────────────────────────────
DB_PATH             = "data/algo_trader.db"

# ─────────────────────────────────────────────────────────────
#  FLASK WEB SERVER
# ─────────────────────────────────────────────────────────────
FLASK_PORT          = int(os.getenv("PORT", 5000))
SECRET_KEY          = os.getenv("SECRET_KEY", "algo-trader-secret-2024")
