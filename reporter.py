"""
=============================================================
  REPORT GENERATOR
  Creates a full multi-panel PNG report every 3 weeks
=============================================================
"""

import os
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")               # headless — no display needed on server
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
from matplotlib.colors import LinearSegmentedColormap
from datetime import datetime, date

from database import (
    get_latest_signals, get_top_bullish, get_all_trades,
    get_market_summary, get_portfolio_pnl_over_time, get_win_prob_history
)
from config import TAKE_PROFIT_PCT, STOP_LOSS_PCT, WIN_BIAS_THRESH


# ── Color palette ────────────────────────────────────────────
BG      = "#080c14"
PANEL   = "#0d1424"
CARD    = "#111827"
GRID    = "#1e293b"
GREEN   = "#00ff88"
RED     = "#ff4757"
BLUE    = "#38bdf8"
PURPLE  = "#a78bfa"
YELLOW  = "#fbbf24"
ORANGE  = "#fb923c"
WHITE   = "#f1f5f9"
GRAY    = "#64748b"
LGRAY   = "#94a3b8"


def _style_ax(ax):
    ax.set_facecolor(PANEL)
    ax.tick_params(colors=LGRAY, labelsize=8)
    ax.grid(color=GRID, linestyle="--", linewidth=0.4, alpha=0.8)
    for spine in ax.spines.values():
        spine.set_edgecolor(GRID)


def generate_report(period_start: str, period_end: str) -> str:
    """
    Build a full A3-landscape report PNG.
    Returns the file path.
    """
    os.makedirs("reports", exist_ok=True)
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M")
    report_path = f"reports/report_{timestamp}.png"

    # ── Fetch data ───────────────────────────────────────────
    top_bullish  = get_top_bullish(15)
    signals      = get_latest_signals(200)
    trades       = get_all_trades(500)
    mkt_summary  = get_market_summary()
    pnl_history  = get_portfolio_pnl_over_time()

    total_trades = len(trades)
    wins         = sum(1 for t in trades if t["result"] == "WIN")
    net_pnl      = sum(t["pnl_pct"] for t in trades)
    win_rate     = (wins / total_trades * 100) if total_trades else 0

    # ── Figure layout ────────────────────────────────────────
    fig = plt.figure(figsize=(22, 16), facecolor=BG)
    fig.patch.set_facecolor(BG)

    # Title bar
    fig.text(0.5, 0.975,
             "ALGO TRADER  ·  GLOBAL MARKET INTELLIGENCE REPORT",
             ha="center", va="top", fontsize=18, fontweight="bold",
             color=WHITE, fontfamily="monospace")
    fig.text(0.5, 0.955,
             f"Period: {period_start}  →  {period_end}   "
             f"·   Generated: {datetime.now().strftime('%d %b %Y  %H:%M IST')}",
             ha="center", va="top", fontsize=9, color=GRAY)

    gs = gridspec.GridSpec(
        3, 4,
        figure=fig,
        top=0.93, bottom=0.04,
        left=0.04, right=0.97,
        hspace=0.45, wspace=0.35
    )

    # ── [0,0:2]  Top Bullish Stocks — Horizontal Bar ─────────
    ax1 = fig.add_subplot(gs[0, :2])
    _style_ax(ax1)
    if top_bullish:
        tickers = [t["ticker"].replace(".NS","").replace(".HK","") for t in top_bullish[:12]]
        probs   = [t["win_prob"] * 100 for t in top_bullish[:12]]
        colors  = [GREEN if p > 60 else BLUE for p in probs]
        bars = ax1.barh(tickers[::-1], probs[::-1], color=colors[::-1],
                        height=0.6, edgecolor=GRID, linewidth=0.5)
        ax1.axvline(60, color=YELLOW, linestyle="--", linewidth=1, alpha=0.7, label="60% threshold")
        ax1.axvline(50, color=ORANGE, linestyle=":",  linewidth=1, alpha=0.6, label="50% threshold")
        for bar, prob in zip(bars, probs[::-1]):
            ax1.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
                     f"{prob:.1f}%", va="center", fontsize=7.5, color=WHITE)
        ax1.set_xlim(0, 105)
        ax1.set_xlabel("Win Probability %", color=LGRAY, fontsize=8)
        ax1.legend(fontsize=7, labelcolor=WHITE, framealpha=0.2)
    ax1.set_title("🏆  Top Bullish Signals — Global", color=WHITE, fontsize=10, pad=8)

    # ── [0,2:4]  Market Heatmap ───────────────────────────────
    ax2 = fig.add_subplot(gs[0, 2:])
    _style_ax(ax2)
    if mkt_summary:
        markets   = [m["market"] for m in mkt_summary]
        avg_probs = [m["avg_win_pct"] for m in mkt_summary]
        bullish_c = [m["bullish"] for m in mkt_summary]
        totals    = [m["total"] for m in mkt_summary]
        x         = np.arange(len(markets))
        bar_colors = [GREEN if p >= 50 else RED for p in avg_probs]
        b = ax2.bar(x, avg_probs, color=bar_colors, alpha=0.8,
                    edgecolor=GRID, linewidth=0.5, width=0.5)
        ax2.axhline(50, color=YELLOW, linestyle="--", linewidth=1, alpha=0.7)
        for i, (bar, pct, bull, tot) in enumerate(zip(b, avg_probs, bullish_c, totals)):
            ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.8,
                     f"{pct:.0f}%\n{bull}/{tot}", ha="center",
                     fontsize=7.5, color=WHITE, fontweight="bold")
        ax2.set_xticks(x)
        ax2.set_xticklabels(markets, color=LGRAY, fontsize=8)
        ax2.set_ylabel("Avg Win Prob %", color=LGRAY, fontsize=8)
        ax2.set_ylim(0, 100)
    ax2.set_title("🌍  Market Heatmap  (Bullish/Total)", color=WHITE, fontsize=10, pad=8)

    # ── [1,0:3]  Portfolio PnL curve ─────────────────────────
    ax3 = fig.add_subplot(gs[1, :3])
    _style_ax(ax3)
    if pnl_history:
        dates    = [p["date"] for p in pnl_history]
        cum_pnl  = np.cumsum([p["daily_pnl"] for p in pnl_history])
        x_vals   = np.arange(len(dates))
        ax3.fill_between(x_vals, cum_pnl, 0,
                          where=(cum_pnl >= 0), alpha=0.25, color=GREEN)
        ax3.fill_between(x_vals, cum_pnl, 0,
                          where=(cum_pnl < 0),  alpha=0.25, color=RED)
        ax3.plot(x_vals, cum_pnl, color=BLUE, linewidth=2, zorder=5)
        ax3.axhline(0, color=GRAY, linewidth=0.8)
        # Label last value
        ax3.annotate(f"{cum_pnl[-1]:+.2f}%",
                     xy=(x_vals[-1], cum_pnl[-1]),
                     xytext=(-30, 10), textcoords="offset points",
                     color=GREEN if cum_pnl[-1] >= 0 else RED,
                     fontsize=9, fontweight="bold")
        step = max(1, len(dates) // 10)
        ax3.set_xticks(x_vals[::step])
        ax3.set_xticklabels(dates[::step], rotation=30, ha="right",
                             fontsize=7, color=LGRAY)
        ax3.set_ylabel("Cumulative PnL %", color=LGRAY, fontsize=8)
    else:
        ax3.text(0.5, 0.5, "No trades yet — data accumulates over time",
                 ha="center", va="center", color=GRAY, fontsize=10,
                 transform=ax3.transAxes)
    ax3.set_title("📈  Cumulative Portfolio PnL  (Simulated)", color=WHITE, fontsize=10, pad=8)

    # ── [1,3]  Summary KPI cards ─────────────────────────────
    ax4 = fig.add_subplot(gs[1, 3])
    ax4.set_facecolor(BG)
    ax4.axis("off")

    kpis = [
        ("TOTAL TRADES",  str(total_trades),        WHITE),
        ("WIN RATE",       f"{win_rate:.1f}%",        GREEN  if win_rate > 50 else RED),
        ("NET PnL",        f"{net_pnl:+.2f}%",       GREEN  if net_pnl > 0   else RED),
        ("WINS",           str(wins),                 GREEN),
        ("LOSSES",         str(total_trades - wins),  RED),
        ("TAKE PROFIT",    f"+{TAKE_PROFIT_PCT*100:.0f}%", YELLOW),
        ("STOP LOSS",      f"-{STOP_LOSS_PCT*100:.0f}%",  ORANGE),
    ]
    for i, (label, val, color) in enumerate(kpis):
        y = 0.95 - i * 0.135
        # Card background
        rect = mpatches.FancyBboxPatch(
            (0.02, y - 0.06), 0.96, 0.10,
            boxstyle="round,pad=0.01",
            facecolor=CARD, edgecolor=GRID, linewidth=0.8,
            transform=ax4.transAxes, clip_on=False
        )
        ax4.add_patch(rect)
        ax4.text(0.08, y - 0.005, label, transform=ax4.transAxes,
                 fontsize=6.5, color=LGRAY, va="center")
        ax4.text(0.92, y - 0.005, val,  transform=ax4.transAxes,
                 fontsize=11, color=color, va="center", ha="right",
                 fontweight="bold")
    ax4.set_title("📊  Period Summary", color=WHITE, fontsize=10, pad=8)

    # ── [2, 0:4]  Win probability distribution histogram ──────
    ax5 = fig.add_subplot(gs[2, :2])
    _style_ax(ax5)
    if signals:
        probs = [s["win_prob"] * 100 for s in signals if s["win_prob"] is not None]
        n, bins, patches = ax5.hist(probs, bins=20, edgecolor=GRID, linewidth=0.5)
        for patch, left_edge in zip(patches, bins[:-1]):
            patch.set_facecolor(GREEN if left_edge >= 60 else
                                 BLUE  if left_edge >= 50 else PURPLE)
        ax5.axvline(60, color=YELLOW, linestyle="--", linewidth=1.2, label="60% auto-buy")
        ax5.axvline(50, color=ORANGE, linestyle=":",  linewidth=1.0, label="50% bullish bias")
        ax5.set_xlabel("Win Probability %", color=LGRAY, fontsize=8)
        ax5.set_ylabel("# Stocks",          color=LGRAY, fontsize=8)
        ax5.legend(fontsize=7, labelcolor=WHITE, framealpha=0.2)
    ax5.set_title("📉  Win Probability Distribution  (All Stocks)", color=WHITE, fontsize=10, pad=8)

    # ── [2, 2:4]  Trade result pie ───────────────────────────
    ax6 = fig.add_subplot(gs[2, 2:])
    ax6.set_facecolor(PANEL)
    if total_trades > 0:
        sizes  = [wins, total_trades - wins]
        labels = [f"Wins\n{wins}", f"Losses\n{total_trades - wins}"]
        colors_pie = [GREEN, RED]
        wedges, texts, autotexts = ax6.pie(
            sizes, labels=labels, colors=colors_pie,
            autopct="%1.1f%%", startangle=90,
            wedgeprops={"edgecolor": BG, "linewidth": 2},
            textprops={"color": WHITE, "fontsize": 9}
        )
        for at in autotexts:
            at.set_color(BG)
            at.set_fontweight("bold")
    else:
        ax6.text(0.5, 0.5, "No trades yet",
                 ha="center", va="center", color=GRAY, fontsize=12,
                 transform=ax6.transAxes)
    ax6.set_title("🎯  Trade Outcome Breakdown", color=WHITE, fontsize=10, pad=8)

    # ── Footer ───────────────────────────────────────────────
    fig.text(0.5, 0.01,
             "⚠  This report is for educational/simulation purposes only. "
             "Not financial advice.   |   Algo Trader v2  ·  github.com/lucky",
             ha="center", fontsize=7, color=GRAY)

    plt.savefig(report_path, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"✅  Report saved → {report_path}")
    return report_path
