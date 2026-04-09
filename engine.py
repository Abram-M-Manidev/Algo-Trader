"""
=============================================================
  ANALYSIS ENGINE  v2  —  Fixed for Render.com free tier
  Uses direct Yahoo Finance API instead of yfinance library
=============================================================
"""

import requests
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

TICKER_TO_MARKET = {
    t: market
    for market, tickers in WATCHLIST.items()
    for t in tickers
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def fetch_data(ticker: str):
    try:
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
            f"?interval=1d&range={LOOKBACK_DAYS}d"
        )
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            url2 = url.replace("query1", "query2")
            r = requests.get(url2, headers=HEADERS, timeout=20)
            if r.status_code != 200:
                return None

        data   = r.json()
        result = data.get("chart", {}).get("result")
        if not result:
            return None

        quotes     = result[0]
        timestamps = quotes.get("timestamp", [])
        ohlcv      = quotes.get("indicators", {}).get("quote", [{}])[0]

        if not timestamps or not ohlcv:
            return None

        from datetime import datetime, timezone
        df = pd.DataFrame({
            "Open":   ohlcv.get("open",   []),
            "High":   ohlcv.get("high",   []),
            "Low":    ohlcv.get("low",    []),
            "Close":  ohlcv.get("close",  []),
            "Volume": ohlcv.get("volume", []),
        }, index=pd.to_datetime(
            [datetime.fromtimestamp(t, tz=timezone.utc) for t in timestamps]
        ))

        df.dropna(inplace=True)
        if len(df) < 30:
            return None
        return df

    except Exception as e:
        print(f"    Warning: Fetch error [{ticker}]: {e}")
        return None


def compute_rsi(series, period=14):
    delta    = series.diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs       = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_macd(series):
    ema_fast    = series.ewm(span=MACD_FAST,   adjust=False).mean()
    ema_slow    = series.ewm(span=MACD_SLOW,   adjust=False).mean()
    macd_line   = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=MACD_SIGNAL, adjust=False).mean()
    return macd_line, signal_line, macd_line - signal_line


def compute_bollinger_bands(series):
    sma = series.rolling(BB_PERIOD).mean()
    std = series.rolling(BB_PERIOD).std()
    return sma + BB_STD * std, sma, sma - BB_STD * std


def compute_adx(df, period=14):
    high  = df["High"]
    low   = df["Low"]
    close = df["Close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    dm_plus  = np.where((high.diff() > low.diff().abs()) & (high.diff() > 0), high.diff(), 0)
    dm_minus = np.where((low.diff().abs() > high.diff()) & (low.diff() < 0), low.diff().abs(), 0)
    atr      = tr.ewm(alpha=1/period, adjust=False).mean()
    di_plus  = 100 * pd.Series(dm_plus,  index=df.index).ewm(alpha=1/period, adjust=False).mean() / atr
    di_minus = 100 * pd.Series(dm_minus, index=df.index).ewm(alpha=1/period, adjust=False).mean() / atr
    dx       = 100 * (di_plus - di_minus).abs() / (di_plus + di_minus).replace(0, np.nan)
    return dx.ewm(alpha=1/period, adjust=False).mean()


def add_indicators(df):
    df = df.copy()
    df["RSI"]                                      = compute_rsi(df["Close"], RSI_PERIOD)
    df["MACD"], df["MACD_Signal"], df["MACD_Hist"] = compute_macd(df["Close"])
    df["BB_Upper"], df["BB_Mid"], df["BB_Lower"]   = compute_bollinger_bands(df["Close"])
    df["ADX"]    = compute_adx(df, ADX_PERIOD)
    df["Vol_MA"] = df["Volume"].rolling(20).mean()
    df["Sig_RSI"]  = df["RSI"] < 30
    df["Sig_MACD"] = (df["MACD"] > df["MACD_Signal"]) & (df["MACD"].shift(1) <= df["MACD_Signal"].shift(1))
    df["Sig_BB"]   = df["Close"] < df["BB_Lower"]
    df["Sig_ADX"]  = df["ADX"] > 25
    df["Sig_Vol"]  = df["Volume"] > df["Vol_MA"] * 1.2
    df["Signal_Score"] = (
        df["Sig_RSI"].astype(int) + df["Sig_MACD"].astype(int) +
        df["Sig_BB"].astype(int)  + df["Sig_ADX"].astype(int)  + df["Sig_Vol"].astype(int)
    )
    df["Win_Signal"] = df["Signal_Score"] >= 2
    return df


def calculate_win_probability(df):
    valid   = df.dropna(subset=["RSI", "MACD", "ADX"])
    total   = len(valid)
    signals = int(valid["Win_Signal"].sum())
    return round(signals / total, 4) if total > 0 else 0.0


def simulate_trades(df, win_prob):
    df = df.copy()
    df["Action"] = ""
    df["Trade_PnL"] = np.nan
    trades = []
    if win_prob <= AUTO_BUY_THRESH:
        return df, trades
    in_trade = False
    entry_price = 0.0
    entry_date  = None
    rows = list(df.itertuples())
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
                    exit_price, result, tag = tp, "WIN", "SELL_WIN"
                else:
                    exit_price, result, tag = sl, "LOSS", "SELL_LOSS"
                pnl = (exit_price - entry_price) / entry_price
                trades.append({
                    "entry_date": str(entry_date.date()), "exit_date": str(row.Index.date()),
                    "entry_price": round(entry_price, 4), "exit_price": round(exit_price, 4),
                    "pnl_pct": round(pnl * 100, 2), "result": result,
                })
                df.at[row.Index, "Action"]    = tag
                df.at[row.Index, "Trade_PnL"] = pnl
                in_trade = False
    if in_trade:
        ep  = rows[-1].Close
        pnl = (ep - entry_price) / entry_price
        trades.append({
            "entry_date": str(entry_date.date()), "exit_date": str(rows[-1].Index.date()),
            "entry_price": round(entry_price, 4), "exit_price": round(ep, 4),
            "pnl_pct": round(pnl * 100, 2), "result": "WIN" if pnl > 0 else "LOSS",
        })
        df.at[rows[-1].Index, "Action"]    = "SELL_WIN" if pnl > 0 else "SELL_LOSS"
        df.at[rows[-1].Index, "Trade_PnL"] = pnl
    return df, trades


def analyze_ticker(ticker: str):
    df = fetch_data(ticker)
    if df is None:
        return None
    df         = add_indicators(df)
    win_prob   = calculate_win_probability(df)
    df, trades = simulate_trades(df, win_prob)
    last       = df.iloc[-1]
    market     = TICKER_TO_MARKET.get(ticker, "OTHER")

    def safe(val):
        try:
            return round(float(val), 4) if not pd.isna(val) else None
        except:
            return None

    return {
        "ticker": ticker, "market": market, "df": df, "trades": trades,
        "win_prob": win_prob,
        "bias": "BULLISH" if win_prob > WIN_BIAS_THRESH else "BEARISH",
        "auto_buy": win_prob > AUTO_BUY_THRESH,
        "last_close":    safe(last["Close"]),
        "last_rsi":      safe(last["RSI"]),
        "last_macd":     safe(last["MACD"]),
        "last_macd_sig": safe(last["MACD_Signal"]),
        "last_bb_upper": safe(last["BB_Upper"]),
        "last_bb_lower": safe(last["BB_Lower"]),
        "last_adx":      safe(last["ADX"]),
    }
