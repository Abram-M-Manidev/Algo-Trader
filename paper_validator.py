"""
=============================================================
  PAPER TRADING VALIDATOR
  Tracks paper trades for 60 days.
  Unlocks real execution only after meeting minimum criteria.

  UNLOCK CONDITIONS (all must pass):
    - Minimum 30 paper trades completed
    - Win rate >= 52%
    - Net PnL > 0%
    - Max consecutive losses <= 5
    - At least 30 calendar days of data
=============================================================
"""

import json
import os
import logging
from datetime import datetime, date, timedelta
from database import get_conn

logger = logging.getLogger(__name__)

# ── Unlock thresholds ─────────────────────────────────────
MIN_TRADES          = 30
MIN_WIN_RATE        = 52.0      # percent
MIN_NET_PNL         = 0.0       # percent
MAX_CONSEC_LOSSES   = 5
MIN_DAYS            = 30        # calendar days of paper trading


def init_paper_tables():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS paper_trades (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker        TEXT,
            market        TEXT,
            entry_date    TEXT,
            exit_date     TEXT,
            entry_price   REAL,
            exit_price    REAL,
            pnl_pct       REAL,
            result        TEXT,
            broker        TEXT,
            notes         TEXT,
            created_at    TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS paper_status (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            checked_at    TEXT,
            total_trades  INTEGER,
            win_rate      REAL,
            net_pnl       REAL,
            max_consec_loss INTEGER,
            days_running  INTEGER,
            unlocked      INTEGER DEFAULT 0,
            reason        TEXT
        )
    """)
    conn.commit()
    conn.close()


def log_paper_trade(trade: dict):
    """Log a paper trade result."""
    conn = get_conn()
    conn.execute("""
        INSERT INTO paper_trades
            (ticker, market, entry_date, exit_date, entry_price,
             exit_price, pnl_pct, result, broker, notes)
        VALUES
            (:ticker,:market,:entry_date,:exit_date,:entry_price,
             :exit_price,:pnl_pct,:result,:broker,:notes)
    """, trade)
    conn.commit()
    conn.close()


def get_paper_trades() -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM paper_trades ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _max_consecutive_losses(trades: list[dict]) -> int:
    """Calculate maximum consecutive losses in trade history."""
    max_streak = current = 0
    for t in sorted(trades, key=lambda x: x["entry_date"]):
        if t["result"] == "LOSS":
            current += 1
            max_streak = max(max_streak, current)
        else:
            current = 0
    return max_streak


def _days_running(trades: list[dict]) -> int:
    """How many calendar days since first paper trade."""
    if not trades:
        return 0
    dates = [t["entry_date"] for t in trades if t["entry_date"]]
    if not dates:
        return 0
    first = datetime.strptime(min(dates), "%Y-%m-%d").date()
    return (date.today() - first).days


def check_unlock_status() -> dict:
    """
    Run all unlock checks. Returns full status dict.
    If all pass → real trading is unlocked.
    """
    init_paper_tables()
    trades = get_paper_trades()

    total         = len(trades)
    wins          = sum(1 for t in trades if t["result"] == "WIN")
    win_rate      = round(wins / total * 100, 2) if total else 0
    net_pnl       = round(sum(t["pnl_pct"] for t in trades), 2)
    max_consec    = _max_consecutive_losses(trades)
    days          = _days_running(trades)

    checks = {
        "trades_ok"   : total >= MIN_TRADES,
        "winrate_ok"  : win_rate >= MIN_WIN_RATE,
        "pnl_ok"      : net_pnl > MIN_NET_PNL,
        "streak_ok"   : max_consec <= MAX_CONSEC_LOSSES,
        "days_ok"     : days >= MIN_DAYS,
    }

    unlocked = all(checks.values())

    reasons = []
    if not checks["trades_ok"]:
        reasons.append(f"Need {MIN_TRADES - total} more trades ({total}/{MIN_TRADES})")
    if not checks["winrate_ok"]:
        reasons.append(f"Win rate {win_rate:.1f}% < {MIN_WIN_RATE}% required")
    if not checks["pnl_ok"]:
        reasons.append(f"Net PnL {net_pnl:.2f}% must be positive")
    if not checks["streak_ok"]:
        reasons.append(f"Max {max_consec} consecutive losses (limit: {MAX_CONSEC_LOSSES})")
    if not checks["days_ok"]:
        remaining = MIN_DAYS - days
        reasons.append(f"Only {days} days of data — need {remaining} more days")

    status = {
        "unlocked"       : unlocked,
        "total_trades"   : total,
        "wins"           : wins,
        "losses"         : total - wins,
        "win_rate"       : win_rate,
        "net_pnl"        : net_pnl,
        "max_consec_loss": max_consec,
        "days_running"   : days,
        "checks"         : checks,
        "blocking_reasons": reasons,
        "message"        : (
            "✅  REAL TRADING UNLOCKED — all criteria met!"
            if unlocked else
            f"🔒  Paper trading — {len(reasons)} criteria not yet met"
        ),
        # Progress toward unlock
        "progress": {
            "trades"  : f"{min(total, MIN_TRADES)}/{MIN_TRADES}",
            "win_rate": f"{win_rate:.1f}%/{MIN_WIN_RATE}%",
            "pnl"     : f"{net_pnl:+.2f}%/>0%",
            "streak"  : f"{max_consec}/≤{MAX_CONSEC_LOSSES}",
            "days"    : f"{days}/{MIN_DAYS}",
        }
    }

    # Save to DB
    conn = get_conn()
    conn.execute("""
        INSERT INTO paper_status
            (checked_at, total_trades, win_rate, net_pnl,
             max_consec_loss, days_running, unlocked, reason)
        VALUES (?,?,?,?,?,?,?,?)
    """, (
        str(datetime.now()), total, win_rate, net_pnl,
        max_consec, days, int(unlocked), "; ".join(reasons)
    ))
    conn.commit()
    conn.close()

    logger.info(status["message"])
    return status


def is_real_trading_allowed() -> bool:
    """Quick check — returns True only if all criteria are met."""
    status = check_unlock_status()
    return status["unlocked"]


def get_paper_summary() -> dict:
    """Summary for dashboard display."""
    return check_unlock_status()
