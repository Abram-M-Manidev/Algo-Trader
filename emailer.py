"""
=============================================================
  EMAIL DELIVERY
  Sends the 3-week report via Gmail SMTP (free forever)
=============================================================
"""

import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText
from email.mime.image     import MIMEImage
from email.mime.base      import MIMEBase
from email               import encoders
from datetime            import datetime

from config import (
    EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT,
    SMTP_HOST, SMTP_PORT
)


def send_report_email(
    report_path: str,
    period_start: str,
    period_end: str,
    total_trades: int,
    win_rate: float,
    net_pnl: float,
    top_bullish: list[dict],
) -> bool:
    """
    Send the periodic report as an email with:
      - HTML body summary
      - PNG chart attached
    Returns True on success.
    """
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = (
            f"📊 Algo Trader Report  |  "
            f"Win Rate: {win_rate:.1f}%  |  "
            f"Net PnL: {net_pnl:+.2f}%  |  "
            f"{period_start} → {period_end}"
        )
        msg["From"] = EMAIL_SENDER
        msg["To"]   = EMAIL_RECIPIENT

        # ── Top bullish table rows ────────────────────────────
        rows_html = ""
        for i, s in enumerate(top_bullish[:10], 1):
            color = "#00ff88" if s["win_prob"] > 0.6 else "#38bdf8"
            rows_html += f"""
            <tr>
              <td style="padding:6px 12px;color:#94a3b8">{i}</td>
              <td style="padding:6px 12px;color:#f1f5f9;font-weight:bold">{s['ticker']}</td>
              <td style="padding:6px 12px;color:#94a3b8">{s['market']}</td>
              <td style="padding:6px 12px;color:{color};font-weight:bold">
                {s['win_prob']*100:.1f}%
              </td>
              <td style="padding:6px 12px;color:{color}">{s['bias']}</td>
            </tr>
            """

        # ── HTML body ─────────────────────────────────────────
        html = f"""
        <!DOCTYPE html>
        <html>
        <body style="background:#080c14;font-family:'Courier New',monospace;
                     color:#f1f5f9;margin:0;padding:24px">

          <div style="max-width:700px;margin:auto">

            <!-- Header -->
            <div style="border-bottom:2px solid #00ff88;padding-bottom:16px;
                        margin-bottom:24px">
              <h1 style="color:#00ff88;font-size:24px;margin:0;letter-spacing:3px">
                ALGO TRADER
              </h1>
              <p style="color:#64748b;margin:4px 0 0">
                Global Market Intelligence  ·
                {datetime.now().strftime("%d %B %Y")}
              </p>
            </div>

            <!-- KPI cards -->
            <div style="display:flex;gap:12px;margin-bottom:24px;flex-wrap:wrap">
              {"".join(f'''
              <div style="flex:1;min-width:130px;background:#0d1424;
                          border:1px solid #1e293b;border-radius:8px;padding:16px;
                          text-align:center">
                <div style="color:#64748b;font-size:10px;letter-spacing:2px">{k}</div>
                <div style="color:{c};font-size:22px;font-weight:bold;margin-top:6px">{v}</div>
              </div>
              ''' for k,v,c in [
                  ("PERIOD", f"{period_start[:10]}", "#38bdf8"),
                  ("TOTAL TRADES", str(total_trades), "#f1f5f9"),
                  ("WIN RATE", f"{win_rate:.1f}%", "#00ff88" if win_rate>=50 else "#ff4757"),
                  ("NET PnL", f"{net_pnl:+.2f}%", "#00ff88" if net_pnl>=0 else "#ff4757"),
              ])}
            </div>

            <!-- Top Bullish Table -->
            <h2 style="color:#38bdf8;font-size:14px;letter-spacing:2px;
                       margin-bottom:12px">
              🏆 TOP BULLISH SIGNALS
            </h2>
            <table style="width:100%;border-collapse:collapse;
                          background:#0d1424;border-radius:8px;overflow:hidden">
              <thead>
                <tr style="background:#111827;border-bottom:1px solid #1e293b">
                  <th style="padding:8px 12px;color:#64748b;text-align:left">#</th>
                  <th style="padding:8px 12px;color:#64748b;text-align:left">TICKER</th>
                  <th style="padding:8px 12px;color:#64748b;text-align:left">MARKET</th>
                  <th style="padding:8px 12px;color:#64748b;text-align:left">WIN PROB</th>
                  <th style="padding:8px 12px;color:#64748b;text-align:left">BIAS</th>
                </tr>
              </thead>
              <tbody>{rows_html}</tbody>
            </table>

            <!-- Chart notice -->
            <p style="color:#64748b;font-size:12px;margin-top:24px;
                      border-top:1px solid #1e293b;padding-top:16px">
              📎 Full analysis chart is attached to this email.<br>
              ⚠ Simulation only — not financial advice.
            </p>

          </div>
        </body>
        </html>
        """

        msg.attach(MIMEText(html, "html"))

        # ── Attach PNG chart ──────────────────────────────────
        if report_path and os.path.exists(report_path):
            with open(report_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={os.path.basename(report_path)}"
            )
            msg.attach(part)

        # ── Send ──────────────────────────────────────────────
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())

        print(f"✅  Report email sent → {EMAIL_RECIPIENT}")
        return True

    except Exception as e:
        print(f"❌  Email failed: {e}")
        return False
