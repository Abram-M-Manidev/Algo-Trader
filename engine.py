"""
=============================================================
  ANALYSIS ENGINE  v2
  Indicators: RSI + MACD + Bollinger Bands + ADX + Volume
=============================================================
"""

import yfinance as yf
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore")

from config import (
    LOOKBACK_DAYS, RSI_PERIOD, MACD_FAST, MACD_SLOW, MACD_SIGNAL,
    BB_PERIOD, BB_STD, ADX_PERIOD,
    TAKE_PROFIT_PCT, STOP_LOSS_PCT,
    WIN_BIAS_THRESH, AUTO_BUY_THRESH, WATCHLIST
)


# ════════════════════════════════════════════════════════════
#  MARKET LOOKUP  — which market group does a ticker belong to?
# ════════════════════════════════════════════════════════════
TICKER_TO_MARKET = {
    t: market
    for market, tickers in WATCHLIST.items()
    for t in tickers
}


# ════════════════════════════════════════════════════════════
#  DATA FETCH
# ════════════════════════════════════════════════════════════
def fetch_data(ticker: str) -> pd.DataFrame | None:
    try:
        df = yf.download(
            ticker,
            period=f"{LOOKBACK_DAYS}d",
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
        if df.empty or len(df) < 30:
            return None

        # Flatten MultiIndex columns
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df.dropna(inplace=True)
        return df
    except Exception as e:
        print(f"    ⚠  Fetch error [{ticker}]: {e}")
        return None


# ════════════════════════════════════════════════════════════
#  INDICATORS
# ════════════════════════════════════════════════════════════
def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta    = series.diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs       = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_macd(series: pd.Series):
    ema_fast    = series.ewm(span=MACD_FAST,   adjust=False).mean()
    ema_slow    = series.ewm(span=MACD_SLOW,   adjust=False).mean()
    macd_line   = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=MACD_SIGNAL, adjust=False).mean()
    histogram   = macd_line - signal_line
    return macd_line, signal_line, histogram


def compute_bollinger_bands(series: pd.Series):
    sma    = series.rolling(BB_PERIOD).mean()
    std    = series.rolling(BB_PERIOD).std()
    upper  = sma + BB_STD * std
    lower  = sma - BB_STD * std
    return upper, sma, lower


def compute_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average Directional Index — measures trend strength (>25 = strong trend)."""
    high  = df["High"]
    low   = df["Low"]
    close = df["Close"]

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)

    dm_plus  = np.where((high.diff() > low.diff().abs()) & (high.diff() > 0),
                         high.diff(), 0)
    dm_minus = np.where((low.diff().abs() > high.diff()) & (low.diff() < 0),
                         low.diff().abs(), 0)

    atr        = tr.ewm(alpha=1/period,  adjust=False).mean()
    di_plus    = 100 * pd.Series(dm_plus,  index=df.index).ewm(alpha=1/period, adjust=False).mean() / atr
    di_minus   = 100 * pd.Series(dm_minus, index=df.index).ewm(alpha=1/period, adjust=False).mean() / atr

    dx  = 100 * (di_plus - di_minus).abs() / (di_plus + di_minus).replace(0, np.nan)
    adx = dx.ewm(alpha=1/period, adjust=False).mean()
    return adx


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # RSI
    df["RSI"] = compute_rsi(df["Close"], RSI_PERIOD)

    # MACD
    df["MACD"], df["MACD_Signal"], df["MACD_Hist"] = compute_macd(df["Close"])

    # Bollinger Bands
    df["BB_Upper"], df["BB_Mid"], df["BB_Lower"] = compute_bollinger_bands(df["Close"])

    # ADX
    df["ADX"] = compute_adx(df, ADX_PERIOD)

    # Volume MA (20-day)
    df["Vol_MA"] = df["Volume"].rolling(20).mean()

    # ── Signal Conditions ────────────────────────────────────
    df["Sig_RSI"]   = df["RSI"] < 30                         # oversold
    df["Sig_MACD"]  = (                                       # bullish crossover
        (df["MACD"] > df["MACD_Signal"]) &
        (df["MACD"].shift(1) <= df["MACD_Signal"].shift(1))
    )
    df["Sig_BB"]    = df["Close"] < df["BB_Lower"]            # below lower band
    df["Sig_ADX"]   = df["ADX"] > 25                          # strong trend
    df["Sig_Vol"]   = df["Volume"] > df["Vol_MA"] * 1.2       # volume surge

    # Win Signal = at least 2 of the 5 conditions fire simultaneously
    df["Signal_Score"] = (
        df["Sig_RSI"].astype(int)  +
        df["Sig_MACD"].astype(int) +
        df["Sig_BB"].astype(int)   +
        df["Sig_ADX"].astype(int)  +
        df["Sig_Vol"].astype(int)
    )
    df["Win_Signal"] = df["Signal_Score"] >= 2

    return df


# ════════════════════════════════════════════════════════════
#  WIN PROBABILITY
# ════════════════════════════════════════════════════════════
def calculate_win_probability(df: pd.DataFrame) -> float:
    valid   = df.dropna(subset=["RSI", "MACD", "ADX"])
    total   = len(valid)
    signals = int(valid["Win_Signal"].sum())
    return round(signals / total, 4) if total > 0 else 0.0


# ════════════════════════════════════════════════════════════
#  TRADE SIMULATION
# ════════════════════════════════════════════════════════════
def simulate_trades(df: pd.DataFrame, win_prob: float) -> tuple[pd.DataFrame, list[dict]]:
    df     = df.copy()
    df["Action"]    = ""
    df["Trade_PnL"] = np.nan
    trades = []

    if win_prob <= AUTO_BUY_THRESH:
        return df, trades

    in_trade    = False
    entry_price = 0.0
    entry_date  = None
    rows        = list(df.itertuples())

    for i, row in enumerate(rows):
        if not in_trade:
            if i > 0 and rows[i-1].Win_Signal:
                entry_price = row.Open
                entry_date  = row.Index
                in_trade    = True
                df.at[row.Index, "Action"] = "BUY"
        else:
            tp = entry_price * (1 + TAKE_PROFIT_PCT)
            sl = entry_price * (1 - STOP_LOSS_PCT)

            hit_tp = row.High >= tp
            hit_sl = row.Low  <= sl

            if hit_tp or hit_sl:
                if hit_tp and hit_sl:
                    exit_price, result, tag = sl, "LOSS", "SELL_LOSS"
                elif hit_tp:
                    exit_price, result, tag = tp, "WIN",  "SELL_WIN"
                else:
                    exit_price, result, tag = sl, "LOSS", "SELL_LOSS"

                pnl = (exit_price - entry_price) / entry_price
                trades.append({
                    "entry_date"  : str(entry_date.date()),
                    "exit_date"   : str(row.Index.date()),
                    "entry_price" : round(entry_price, 4),
                    "exit_price"  : round(exit_price,  4),
                    "pnl_pct"     : round(pnl * 100, 2),
                    "result"      : result,
                })
                df.at[row.Index, "Action"]    = tag
                df.at[row.Index, "Trade_PnL"] = pnl
                in_trade = False

    if in_trade:
        ep  = rows[-1].Close
        pnl = (ep - entry_price) / entry_price
        result = "WIN" if pnl > 0 else "LOSS"
        trades.append({
            "entry_date"  : str(entry_date.date()),
            "exit_date"   : str(rows[-1].Index.date()),
            "entry_price" : round(entry_price, 4),
            "exit_price"  : round(ep, 4),
            "pnl_pct"     : round(pnl * 100, 2),
            "result"      : result,
        })
        df.at[rows[-1].Index, "Action"]    = "SELL_WIN" if pnl > 0 else "SELL_LOSS"
        df.at[rows[-1].Index, "Trade_PnL"] = pnl

    return df, trades


# ════════════════════════════════════════════════════════════
#  FULL SINGLE-TICKER ANALYSIS  (called by scheduler)
# ════════════════════════════════════════════════════════════
def analyze_ticker(ticker: str) -> dict | None:
    """
    Returns a result dict with all data needed for DB storage,
    or None if data couldn't be fetched.
    """
    df = fetch_data(ticker)
    if df is None:
        return None

    df       = add_indicators(df)
    win_prob = calculate_win_probability(df)
    df, trades = simulate_trades(df, win_prob)

    last = df.iloc[-1]
    market = TICKER_TO_MARKET.get(ticker, "OTHER")

    return {
        "ticker"       : ticker,
        "market"       : market,
        "df"           : df,
        "trades"       : trades,
        "win_prob"     : win_prob,
        "bias"         : "BULLISH" if win_prob > WIN_BIAS_THRESH else "BEARISH",
        "auto_buy"     : win_prob > AUTO_BUY_THRESH,
        "last_close"   : round(float(last["Close"]), 4),
        "last_rsi"     : round(float(last["RSI"]),   2) if not pd.isna(last["RSI"]) else None,
        "last_macd"    : round(float(last["MACD"]),  4) if not pd.isna(last["MACD"]) else None,
        "last_macd_sig": round(float(last["MACD_Signal"]), 4) if not pd.isna(last["MACD_Signal"]) else None,
        "last_bb_upper": round(float(last["BB_Upper"]), 4) if not pd.isna(last["BB_Upper"]) else None,
        "last_bb_lower": round(float(last["BB_Lower"]), 4) if not pd.isna(last["BB_Lower"]) else None,
        "last_adx"     : round(float(last["ADX"]),   2) if not pd.isna(last["ADX"]) else None,
    }
