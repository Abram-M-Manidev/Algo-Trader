"""
=============================================================
  MAIN ENTRY POINT
  Flask + APScheduler wired for production (Render.com)
=============================================================
"""

import atexit, logging, os
from flask import Flask, render_template, jsonify, send_file, abort
from config import FLASK_PORT, SECRET_KEY
from database import (
    init_db, get_latest_signals, get_top_bullish, get_all_trades,
    get_market_summary, get_portfolio_pnl_over_time,
    get_win_prob_history, get_all_reports
)

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S")

app = Flask(__name__)
app.secret_key = SECRET_KEY

@app.route("/")
def index(): return render_template("index.html")

@app.route("/api/summary")
def api_summary():
    trades  = get_all_trades(); signals = get_latest_signals()
    mkt     = get_market_summary(); top = get_top_bullish(10)
    wins    = sum(1 for t in trades if t["result"] == "WIN")
    total   = len(trades); net_pnl = sum(t["pnl_pct"] for t in trades)
    return jsonify({
        "total_trades": total, "win_rate": round(wins/total*100,1) if total else 0,
        "net_pnl": round(net_pnl,2), "wins": wins, "losses": total-wins,
        "total_signals": len(signals),
        "bullish_count": sum(1 for s in signals if s["bias"]=="BULLISH"),
        "market_summary": mkt, "top_bullish": top,
    })

@app.route("/api/signals")
def api_signals(): return jsonify(get_latest_signals(200))

@app.route("/api/trades")
def api_trades(): return jsonify(get_all_trades(500))

@app.route("/api/pnl_history")
def api_pnl_history(): return jsonify(get_portfolio_pnl_over_time())

@app.route("/api/win_history/<ticker>")
def api_win_history(ticker): return jsonify(get_win_prob_history(ticker.upper()))

@app.route("/api/reports")
def api_reports(): return jsonify(get_all_reports())

@app.route("/reports/<filename>")
def serve_report(filename):
    path = os.path.join("reports", filename)
    if not os.path.exists(path): abort(404)
    return send_file(path, mimetype="image/png")

@app.route("/health")
def health(): return jsonify({"status": "ok", "service": "algo-trader"}), 200

@app.route("/api/paper_status")
def api_paper_status():
    from paper_validator import get_paper_summary
    return jsonify(get_paper_summary())

@app.route("/api/broker_status")
def api_broker_status():
    mode = os.getenv("EXECUTION_MODE", "paper")
    status = {"mode": mode, "zerodha_ready": False, "alpaca_ready": False, "alpaca_paper": True}
    try:
        from broker_zerodha import kite_broker
        status["zerodha_ready"] = kite_broker.ready
    except: pass
    try:
        from broker_alpaca import alpaca_broker
        status["alpaca_ready"] = alpaca_broker.ready
        status["alpaca_paper"] = getattr(alpaca_broker, "paper", True)
    except: pass
    return jsonify(status)

@app.route("/api/kite_login_url")
def api_kite_login():
    try:
        from broker_zerodha import kite_broker
        return jsonify({"url": kite_broker.get_login_url()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/kite_token/<request_token>")
def api_kite_token(request_token):
    try:
        from broker_zerodha import kite_broker
        return jsonify(kite_broker.generate_access_token(request_token))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Start scheduler once (safe for gunicorn single-worker)
init_db()
from scheduler import create_scheduler
_scheduler = create_scheduler()
atexit.register(lambda: _scheduler.shutdown(wait=False))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=FLASK_PORT, debug=False)
