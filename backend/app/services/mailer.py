"""Outgoing email. Without SMTP_HOST every message is written to data/outbox/ instead, so links can be opened locally."""
from __future__ import annotations
import html
import logging
import re
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from ..config import get_settings

log = logging.getLogger("adem.mail")


def _page(heading: str, lines: list[str], button: tuple[str, str] | None) -> str:
    body = "".join(f"<p style='margin:0 0 12px'>{html.escape(t)}</p>" for t in lines)
    if button:
        label, url = button
        body += (f"<p style='margin:20px 0'><a href='{html.escape(url)}' style='background:#0f766e;color:#fff;"
                 f"padding:10px 18px;border-radius:6px;text-decoration:none;font-weight:600'>{html.escape(label)}</a></p>"
                 f"<p style='margin:0;color:#5a655f;font-size:12px'>Or open: {html.escape(url)}</p>")
    return (f"<div style='font-family:Segoe UI,Arial,sans-serif;max-width:520px;margin:auto;color:#18211d'>"
            f"<h2 style='color:#0e5e70'>{html.escape(heading)}</h2>{body}"
            f"<p style='margin-top:28px;color:#5a655f;font-size:12px'>ADEM: AI-assisted exam evaluation</p></div>")


def send(to: str, subject: str, heading: str, lines: list[str], button: tuple[str, str] | None = None) -> None:
    s = get_settings()
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.smtp_from, to, subject
    text = "\n\n".join(lines) + (f"\n\n{button[0]}: {button[1]}" if button else "")
    msg.set_content(text)
    msg.add_alternative(_page(heading, lines, button), subtype="html")
    if not s.smtp_host:
        out = s.data_path / "outbox"
        out.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        name = re.sub(r"[^\w.@-]", "_", to)
        (out / f"{stamp}_{name}.eml").write_bytes(bytes(msg))
        log.info("Email to %s (%s) written to outbox: %s", to, subject, button[1] if button else "")
        return
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
            if s.smtp_starttls:
                smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)
    except (OSError, smtplib.SMTPException):
        # a failed email must not fail the request that triggered it; the user can ask again
        log.exception("Could not send email to %s (%s)", to, subject)
