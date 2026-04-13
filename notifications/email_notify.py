"""Email notifications — sends deal alerts via SMTP."""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import settings


def send_email(subject: str, html_body: str) -> bool:
    """Send an HTML email using the configured SMTP settings. Returns True on success."""
    if not settings.EMAIL_ENABLED:
        print("[email] Email notifications disabled (set EMAIL_ENABLED=true to enable)")
        return False

    if not all([settings.EMAIL_SENDER, settings.EMAIL_PASSWORD, settings.EMAIL_RECIPIENT]):
        print("[email] Missing EMAIL_SENDER, EMAIL_PASSWORD, or EMAIL_RECIPIENT")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_SENDER
    msg["To"] = settings.EMAIL_RECIPIENT
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(settings.EMAIL_SMTP_HOST, settings.EMAIL_SMTP_PORT) as server:
            server.starttls()
            server.login(settings.EMAIL_SENDER, settings.EMAIL_PASSWORD)
            server.send_message(msg)
        print(f"[email] Sent to {settings.EMAIL_RECIPIENT}")
        return True
    except Exception as exc:
        print(f"[email] Failed to send: {exc}")
        return False


def notify_deals_email(deals: list[dict]) -> bool:
    """Send a deal summary email."""
    if not deals:
        return False

    rows = ""
    for d in deals[:10]:
        dest = d.get("destination", "?")
        score = d.get("score", 0)
        flight = d.get("price_usd", 0)
        hotel_total = d.get("best_stay", {}).get("total_price", 0)
        total = d.get("estimated_total", d.get("total_trip_cost", 0))
        dates = f"{d.get('outbound_date', '')} - {d.get('return_date', '')}"
        drop = d.get("price_drop")
        drop_str = f" (<span style='color:green'>-${drop:.0f}</span>)" if drop and drop > 0 else ""

        rows += (
            f"<tr>"
            f"<td style='padding:8px;border-bottom:1px solid #ddd'><strong>{dest}</strong></td>"
            f"<td style='padding:8px;border-bottom:1px solid #ddd'>{score}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #ddd'>${flight:.0f}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #ddd'>${hotel_total:.0f}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #ddd'><strong>${total:.0f}</strong>{drop_str}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #ddd'>{dates}</td>"
            f"</tr>"
        )

    html = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:700px;">
    <h2>Weekend Deal Hunter: {len(deals)} new deal{"s" if len(deals) > 1 else ""}!</h2>
    <table style="border-collapse:collapse;width:100%;">
    <tr style="background:#f5f5f5;">
        <th style="padding:8px;text-align:left">Destination</th>
        <th style="padding:8px;text-align:left">Score</th>
        <th style="padding:8px;text-align:left">Flight</th>
        <th style="padding:8px;text-align:left">Hotel</th>
        <th style="padding:8px;text-align:left">Est. Total</th>
        <th style="padding:8px;text-align:left">Dates</th>
    </tr>
    {rows}
    </table>
    <p style="color:#888;margin-top:16px;font-size:13px;">
        Open your local dashboard for full details and recommendations.
    </p>
    </body></html>
    """

    return send_email(
        f"Weekend Deals: {len(deals)} found - best is {deals[0].get('destination', '?')}",
        html,
    )
