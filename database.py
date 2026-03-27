"""
=============================================================
  DATABASE LAYER
  SQLite-backed storage for signals, trades, and reports
=============================================================
"""

import sqlite3
import os
import json
from datetime import datetime
from config import DB_PATH


def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create all tables if they don't exist."""
    conn = get_conn()
    c = conn.cursor()

    # ── Daily signal snapshot per ticker ─────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date      TEXT NOT NULL,
            ticker        TEXT NOT NULL,
            market        TEXT NOT NULL,
            close         REAL,
            rsi           REAL,
            macd          REAL,
            macd_signal   REAL,
            bb_upper      REAL,
            bb_lower      REAL,
            adx           REAL,
            win_signal    INTEGER,
            win_prob      REAL,
            bias          TEXT,
            UNIQUE(run_date, ticker)
        )
    """)

    # ── Simulated trades ─────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker        TEXT NOT NULL,
            market        TEXT NOT NULL,
            entry_date    TEXT,
            exit_date     TEXT,
            entry_price   REAL,
            exit_price    REAL,
            pnl_pct       REAL,
            result        TEXT,
            created_at    TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Periodic reports ─────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date   TEXT NOT NULL,
            period_start  TEXT,
            period_end    TEXT,
            total_trades  INTEGER,
            win_rate      REAL,
            net_pnl       REAL,
            top_bullish   TEXT,
            report_path   TEXT,
            sent_email    INTEGER DEFAULT 0,
            created_at    TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── System run log ────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS run_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at        TEXT DEFAULT CURRENT_TIMESTAMP,
            tickers_total INTEGER,
            tickers_ok    INTEGER,
            tickers_err   INTEGER,
            duration_sec  REAL,
            notes         TEXT
        )
    """)

    conn.commit()
    conn.close()
    print("✅  Database initialized.")


def upsert_signal(data: dict):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO signals
            (run_date, ticker, market, close, rsi, macd, macd_signal,
             bb_upper, bb_lower, adx, win_signal, win_prob, bias)
        VALUES
            (:run_date,:ticker,:market,:close,:rsi,:macd,:macd_signal,
             :bb_upper,:bb_lower,:adx,:win_signal,:win_prob,:bias)
        ON CONFLICT(run_date, ticker) DO UPDATE SET
            close=excluded.close, rsi=excluded.rsi,
            macd=excluded.macd, win_prob=excluded.win_prob,
            bias=excluded.bias
    """, data)
    conn.commit()
    conn.close()


def insert_trade(data: dict):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO trades
            (ticker, market, entry_date, exit_date,
             entry_price, exit_price, pnl_pct, result)
        VALUES
            (:ticker,:market,:entry_date,:exit_date,
             :entry_price,:exit_price,:pnl_pct,:result)
    """, data)
    conn.commit()
    conn.close()


def insert_report(data: dict):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO reports
            (report_date, period_start, period_end, total_trades,
             win_rate, net_pnl, top_bullish, report_path)
        VALUES
            (:report_date,:period_start,:period_end,:total_trades,
             :win_rate,:net_pnl,:top_bullish,:report_path)
    """, data)
    rid = c.lastrowid
    conn.commit()
    conn.close()
    return rid


def mark_report_sent(report_id: int):
    conn = get_conn()
    conn.execute("UPDATE reports SET sent_email=1 WHERE id=?", (report_id,))
    conn.commit()
    conn.close()


def log_run(data: dict):
    conn = get_conn()
    conn.execute("""
        INSERT INTO run_log (tickers_total, tickers_ok, tickers_err, duration_sec, notes)
        VALUES (:tickers_total,:tickers_ok,:tickers_err,:duration_sec,:notes)
    """, data)
    conn.commit()
    conn.close()


# ── Read helpers (used by Flask dashboard) ───────────────────

def get_latest_signals(limit=200):
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM signals
        WHERE run_date = (SELECT MAX(run_date) FROM signals)
        ORDER BY win_prob DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_top_bullish(n=10):
    conn = get_conn()
    rows = conn.execute("""
        SELECT ticker, market, win_prob, bias, close, rsi
        FROM signals
        WHERE run_date = (SELECT MAX(run_date) FROM signals)
          AND bias = 'BULLISH'
        ORDER BY win_prob DESC
        LIMIT ?
    """, (n,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_trades(limit=500):
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM trades ORDER BY created_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_win_prob_history(ticker: str, days=90):
    conn = get_conn()
    rows = conn.execute("""
        SELECT run_date, win_prob, bias, close
        FROM signals
        WHERE ticker=?
        ORDER BY run_date DESC
        LIMIT ?
    """, (ticker, days)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_reports():
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM reports ORDER BY report_date DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_market_summary():
    """Aggregate win rates per market for dashboard."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT market,
               COUNT(*) as total,
               SUM(CASE WHEN bias='BULLISH' THEN 1 ELSE 0 END) as bullish,
               ROUND(AVG(win_prob)*100, 1) as avg_win_pct
        FROM signals
        WHERE run_date = (SELECT MAX(run_date) FROM signals)
        GROUP BY market
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_portfolio_pnl_over_time():
    conn = get_conn()
    rows = conn.execute("""
        SELECT exit_date as date,
               ROUND(SUM(pnl_pct), 2) as daily_pnl,
               COUNT(*) as trades
        FROM trades
        WHERE exit_date IS NOT NULL
        GROUP BY exit_date
        ORDER BY exit_date
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]
