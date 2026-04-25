from __future__ import annotations

import json
import smtplib
from email.mime.text import MIMEText
from urllib import request as urlrequest

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


def _send_smtp(to_email: str, subject: str, body: str) -> None:
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM_EMAIL
    msg["To"] = to_email
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
        server.starttls()
        if settings.SMTP_USER:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(settings.SMTP_FROM_EMAIL, [to_email], msg.as_string())


def _send_sendgrid(to_email: str, subject: str, body: str) -> None:
    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": settings.SENDGRID_FROM_EMAIL},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
    }
    req = urlrequest.Request(
        "https://api.sendgrid.com/v3/mail/send",
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    with urlrequest.urlopen(req, timeout=10) as _:
        return


def _send_email(to_email: str, subject: str, body: str) -> None:
    if not settings.ENABLE_EMAIL:
        logger.info("email_skipped", extra={"event": "email_skipped", "to": to_email, "subject": subject})
        return
    try:
        if settings.EMAIL_PROVIDER.lower() == "sendgrid":
            _send_sendgrid(to_email, subject, body)
        else:
            _send_smtp(to_email, subject, body)
    except Exception as exc:
        logger.warning("email_send_failed", extra={"event": "email_send_failed", "to": to_email, "error": str(exc)})


def send_welcome_email(to_email: str, company_name: str) -> None:
    _send_email(
        to_email,
        "Welcome to Nerox",
        f"Welcome to Nerox, {company_name}. Your account is ready.",
    )


def send_password_reset_email(to_email: str, company_name: str, reset_url: str) -> None:
    _send_email(
        to_email,
        "Reset your Nerox password",
        f"Hi {company_name},\n\nUse this link to reset your password:\n{reset_url}\n\nIf you did not request this, ignore this email.",
    )


def send_alert_email(to_email: str, severity: str, message: str) -> None:
    _send_email(
        to_email,
        f"Nerox Alert ({severity.upper()})",
        message,
    )
