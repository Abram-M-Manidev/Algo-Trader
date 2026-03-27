"""
=============================================================
  SCHEDULER
  Runs daily analysis + triggers 3-week reports automatically
  Uses APScheduler — runs inside the same Flask process
=============================================================
"""

import time
import traceback
from datetime import datetime, date, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron         import CronTrigger

from config      import (
    ALL_TICKERS, DAILY_RUN_HOUR, DAILY_RUN_MINUTE,
    REPORT_INTERVAL_WEEKS
)
from engine      import analyze_ticker
from database    import (
    init_db, upsert_signal, insert_trade, insert_report,
    mark_report_sent, log_run, get_top_bullish, get_all_trades,
    get_all_reports
)
from reporter    import generate_report
from emailer     import send_report_email


# ════════════════════════════════════════════════════════════
#  DAILY JOB — analyze every ticker, store to DB
# ════════════════════════════════════════════════════════════
def run_daily_analysis():
    start_time = time.time()
    today      = str(date.today())
    ok = err   = 0

    print(f"\n{'='*60}")
    print(f"  DAILY RUN  —  {today}  ({len(ALL_TICKERS)} tickers)")
    print(f"{'='*60}")

    for ticker in ALL_TICKERS:
        try:
            result = analyze_ticker(ticker)
            if result is None:
                err += 1
                continue

            # Store signal snapshot
            upsert_signal({
                "run_date"     : today,
                "ticker"       : ticker,
                "market"       : result["market"],
                "close"        : result["last_close"],
                "rsi"          : result["last_rsi"],
                "macd"         : result["last_macd"],
                "macd_signal"  : result["last_macd_sig"],
                "bb_upper"     : result["last_bb_upper"],
                "bb_lower"     : result["last_bb_lower"],
                "adx"          : result["last_adx"],
                "win_signal"   : int(result["df"]["Win_Signal"].iloc[-1]),
                "win_prob"     : result["win_prob"],
                "bias"         : result["bias"],
            })

            # Store any new simulated trades
            for t in result["trades"]:
                insert_trade({
                    "ticker"      : ticker,
                    "market"      : result["market"],
                    "entry_date"  : t["entry_date"],
                    "exit_date"   : t["exit_date"],
                    "entry_price" : t["entry_price"],
                    "exit_price"  : t["exit_price"],
                    "pnl_pct"     : t["pnl_pct"],
                    "result"      : t["result"],
                })

            bias_tag = "🟢" if result["bias"] == "BULLISH" else "🔴"
            print(f"  {bias_tag}  {ticker:<18}  "
                  f"WinProb={result['win_prob']:.1%}  "
                  f"RSI={result['last_rsi'] or 'N/A'}")
            ok += 1

        except Exception as e:
            print(f"  ❌  {ticker}: {e}")
            err += 1

    duration = round(time.time() - start_time, 1)
    log_run({
        "tickers_total": len(ALL_TICKERS),
        "tickers_ok"   : ok,
        "tickers_err"  : err,
        "duration_sec" : duration,
        "notes"        : f"Daily run completed in {duration}s",
    })

    print(f"\n✅  Done: {ok} OK, {err} errors, {duration}s elapsed")

    # Check if a periodic report is due
    _maybe_send_periodic_report(today)


# ════════════════════════════════════════════════════════════
#  PERIODIC REPORT  — every REPORT_INTERVAL_WEEKS weeks
# ════════════════════════════════════════════════════════════
def _maybe_send_periodic_report(today_str: str):
    reports = get_all_reports()

    if reports:
        last_date = datetime.strptime(reports[0]["report_date"], "%Y-%m-%d").date()
        days_since = (date.today() - last_date).days
        if days_since < (REPORT_INTERVAL_WEEKS * 7):
            print(f"  ℹ  Next report in {(REPORT_INTERVAL_WEEKS*7 - days_since)} days.")
            return

    # Time to generate!
    period_end   = today_str
    period_start = str(date.today() - timedelta(weeks=REPORT_INTERVAL_WEEKS))

    print(f"\n📋  Generating periodic report ({period_start} → {period_end}) …")

    try:
        report_path = generate_report(period_start, period_end)

        all_trades  = get_all_trades()
        top_bullish = get_top_bullish(10)
        wins        = sum(1 for t in all_trades if t["result"] == "WIN")
        total       = len(all_trades)
        win_rate    = (wins / total * 100) if total else 0
        net_pnl     = sum(t["pnl_pct"] for t in all_trades)

        rid = insert_report({
            "report_date" : today_str,
            "period_start": period_start,
            "period_end"  : period_end,
            "total_trades": total,
            "win_rate"    : round(win_rate, 2),
            "net_pnl"     : round(net_pnl,  2),
            "top_bullish" : str([t["ticker"] for t in top_bullish[:5]]),
            "report_path" : report_path,
        })

        success = send_report_email(
            report_path  = report_path,
            period_start = period_start,
            period_end   = period_end,
            total_trades = total,
            win_rate     = win_rate,
            net_pnl      = net_pnl,
            top_bullish  = top_bullish,
        )

        if success:
            mark_report_sent(rid)

    except Exception as e:
        print(f"❌  Report generation failed: {e}")
        traceback.print_exc()


# ════════════════════════════════════════════════════════════
#  SCHEDULER FACTORY
# ════════════════════════════════════════════════════════════
def create_scheduler() -> BackgroundScheduler:
    """
    Returns a started BackgroundScheduler.
    Call this once from app.py — runs alongside Flask.
    """
    init_db()

    scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

    # ── Daily analysis job ────────────────────────────────────
    scheduler.add_job(
        run_daily_analysis,
        trigger=CronTrigger(
            hour=DAILY_RUN_HOUR,
            minute=DAILY_RUN_MINUTE,
            timezone="Asia/Kolkata"
        ),
        id="daily_analysis",
        name="Daily Market Analysis",
        replace_existing=True,
        misfire_grace_time=3600,   # tolerate up to 1h delay (cloud sleep)
    )

    # ── Startup run (run once immediately on server boot) ─────
    scheduler.add_job(
        run_daily_analysis,
        trigger="date",
        run_date=datetime.now(),
        id="startup_run",
        name="Startup Analysis",
    )

    scheduler.start()
    print("🕐  Scheduler started — daily analysis at "
          f"{DAILY_RUN_HOUR:02d}:{DAILY_RUN_MINUTE:02d} IST")
    return scheduler
