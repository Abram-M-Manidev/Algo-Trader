# 🤖 Algo Trader v2 — Global Market Intelligence System

Tracks 65+ stocks across 5 markets. Runs daily. Sends 3-week reports.
Connects to real brokers only after your paper record earns it.

---

## 📁 Files

```
algo_trader/
├── app.py               ← Flask web server
├── config.py            ← All settings
├── engine.py            ← 5-indicator analysis
├── database.py          ← SQLite storage
├── scheduler.py         ← Daily job + 3-week reports
├── reporter.py          ← PNG chart generator
├── emailer.py           ← Gmail delivery
├── broker_zerodha.py    ← Zerodha Kite (NSE real trades)
├── broker_alpaca.py     ← Alpaca (US real/paper trades)
├── paper_validator.py   ← Unlock gate for real trading
├── executor.py          ← Safety-gated execution engine
├── requirements.txt
├── Procfile
├── render.yaml
└── templates/index.html ← Live dashboard
```

---

## 🚀 Deploy on Render (Free)

1. Push folder to a GitHub repo
2. render.com → New Web Service → connect repo → Apply
3. Set env vars (see table below)
4. uptimerobot.com → ping `/health` every 5 min

### Environment Variables

| Variable | Value |
|----------|-------|
| EMAIL_SENDER | your Gmail |
| EMAIL_PASSWORD | Gmail App Password (myaccount.google.com → Security → App Passwords) |
| EMAIL_RECIPIENT | where reports go |
| EXECUTION_MODE | `paper` to start |
| KITE_API_KEY | from kite.trade (Zerodha) |
| KITE_API_SECRET | from kite.trade |
| ALPACA_API_KEY | from alpaca.markets (free) |
| ALPACA_API_SECRET | from alpaca.markets |
| ALPACA_PAPER | `true` until ready |
| MAX_POSITION_INR | `5000` |
| MAX_POSITION_USD | `100` |
| MAX_DAILY_TRADES | `3` |

---

## 🔄 4-Stage Journey to Real Trading

**Stage 1** — `EXECUTION_MODE=paper` → watch signals for 30+ days

**Stage 2** — Dashboard shows unlock progress. All 5 must pass:
- 30+ trades, Win rate ≥52%, Net PnL >0%, Max losing streak ≤5, 30+ days

**Stage 3** — Alpaca US stocks (free API, paper first then live)

**Stage 4** — Zerodha NSE (₹2000/year API, real Indian stocks)

---

## 🛡️ 6 Safety Gates Per Trade

Daily limit → Daily loss breaker → No duplicates → Paper validator → Market open → Position size limit → Order placed with automatic TP/SL

---

## ⚠️ Disclaimer

Simulation and education only. Not financial advice. Start with paper mode.
