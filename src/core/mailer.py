"""Outbound email — SMTP when configured, a dev-mode fallback otherwise.

Email verification and password reset both need to deliver a link. When SMTP is
configured (ATHENA_SMTP_HOST + friends) we send a real message; otherwise — the
common case for a local install — we run in "dev mode": the link is logged and
handed back to the caller so the UI can surface it directly, so the flow still
works with zero email setup. Set ATHENA_ENV=production to disable that fallback.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage

from core.observability import log_json


def smtp_configured() -> bool:
    return bool(os.environ.get("ATHENA_SMTP_HOST"))


def is_production() -> bool:
    return os.environ.get("ATHENA_ENV", "").lower() == "production"


def dev_mode() -> bool:
    """True when we can safely hand verification/reset links back to the client
    (no real email configured and not a production deployment)."""
    return not smtp_configured() and not is_production()


def send_email(to: str, subject: str, body: str) -> bool:
    host = os.environ.get("ATHENA_SMTP_HOST")
    if not host:
        return False
    port = int(os.environ.get("ATHENA_SMTP_PORT", "587"))
    user = os.environ.get("ATHENA_SMTP_USER")
    password = os.environ.get("ATHENA_SMTP_PASSWORD")
    sender = os.environ.get("ATHENA_SMTP_FROM", user or "athena@localhost")
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=15) as s:
                if user:
                    s.login(user, password or "")
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=15) as s:
                s.ehlo()
                try:
                    s.starttls(context=ssl.create_default_context())
                    s.ehlo()
                except smtplib.SMTPException:
                    pass  # server without STARTTLS (e.g. a local relay)
                if user:
                    s.login(user, password or "")
                s.send_message(msg)
        return True
    except Exception as e:  # noqa: BLE001 - a delivery failure shouldn't 500 the request
        log_json("email", action="send_failed", to=to, error=str(e))
        return False


def deliver_link(to: str, subject: str, intro: str, link: str) -> dict:
    """Send a transactional link email. Returns {sent, dev_link}: in dev mode the
    link comes back so the UI can show it; in production it never does."""
    body = f"{intro}\n\n{link}\n\nIf you didn't request this, you can ignore this email."
    sent = send_email(to, subject, body)
    if sent:
        return {"sent": True, "dev_link": None}
    log_json("email", action="dev_link", to=to, subject=subject, link=link)
    return {"sent": False, "dev_link": link if dev_mode() else None}
