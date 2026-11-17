import json
import logging
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage

from app.config import get_settings

logger = logging.getLogger(__name__)


def _send_via_brevo_api(recipient: str, code: str, settings) -> bool:
    """Send transactional email using Brevo's HTTPS REST API (port 443).

    Cloud providers such as Render block outbound TCP on ports 25, 465, and 587.
    HTTPS over port 443 is unrestricted, allowing reliable delivery.
    """
    api_key = (getattr(settings, "brevo_api_key", "") or settings.smtp_password or "").strip()
    from_email = (settings.smtp_from_email or "").strip()
    if not api_key or not from_email:
        return False

    is_brevo = (
        bool(getattr(settings, "brevo_api_key", ""))
        or "brevo" in (settings.smtp_host or "").lower()
        or "sendinblue" in (settings.smtp_host or "").lower()
        or api_key.startswith(("xkeysib-", "xsmtpsib-"))
    )
    if not is_brevo:
        return False

    url = "https://api.brevo.com/v3/smtp/email"
    payload = {
        "sender": {"name": "NeighborLend", "email": from_email},
        "to": [{"email": recipient.strip()}],
        "subject": "Your NeighborLend verification code",
        "htmlContent": (
            f"<div style='font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, sans-serif; "
            f"max-width: 480px; margin: 0 auto; padding: 32px 24px; background: #FFEED6; border-radius: 12px; color: #2B061E;'>"
            f"<h2 style='margin-top: 0; color: #2B061E; font-size: 22px;'>Welcome to NeighborLend!</h2>"
            f"<p style='font-size: 15px; line-height: 1.5; color: #4A3630;'>Enter the verification code below to verify your email address and activate your account:</p>"
            f"<div style='margin: 24px 0; padding: 16px; background: #FFFFFF; border: 2px solid #D2BF55; "
            f"border-radius: 8px; text-align: center; font-size: 32px; font-weight: 700; letter-spacing: 6px; color: #2B061E;'>"
            f"{code}"
            f"</div>"
            f"<p style='font-size: 13px; color: #76575D;'>This code expires in 10 minutes. If you did not request this code, you can safely ignore this email.</p>"
            f"</div>"
        ),
        "textContent": (
            f"Your NeighborLend verification code is {code}.\n\n"
            f"It expires in 10 minutes. If you did not request this code, you can ignore this email."
        ),
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "NeighborLend/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status in (200, 201, 202):
                logger.info("Successfully delivered verification email via Brevo HTTPS API to %s", recipient)
                return True
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="ignore")
        logger.warning("Brevo HTTPS API delivery failed (HTTP %s): %s", exc.code, err_body)
    except Exception as exc:
        logger.warning("Brevo HTTPS API request failed: %s", exc)

    return False


def send_verification_code(recipient: str, code: str) -> None:
    settings = get_settings()
    if not settings.smtp_host and not settings.smtp_password:
        raise RuntimeError("Email delivery is not configured")
    if not settings.smtp_from_email:
        raise RuntimeError("Email delivery is not configured")

    # 1. Prefer Brevo HTTPS REST API (port 443 — bypasses cloud SMTP port blocks)
    if _send_via_brevo_api(recipient, code, settings):
        return

    # 2. Fall back to standard SMTP socket if API was not applicable or failed
    if not settings.smtp_host:
        raise RuntimeError("SMTP host is not configured")

    message = EmailMessage()
    message["Subject"] = "Your NeighborLend verification code"
    message["From"] = settings.smtp_from_email
    message["To"] = recipient
    message.set_content(
        f"Your NeighborLend verification code is {code}.\n\n"
        "It expires in 10 minutes. If you did not request this code, you can "
        "ignore this email."
    )

    try:
        if settings.smtp_use_tls and settings.smtp_port == 465:
            with smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                context=ssl.create_default_context(),
                timeout=8,
            ) as server:
                _send_message(server, message, settings.smtp_username, settings.smtp_password)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=8) as server:
                if settings.smtp_use_tls:
                    server.starttls(context=ssl.create_default_context())
                _send_message(server, message, settings.smtp_username, settings.smtp_password)
    except (OSError, smtplib.SMTPException) as exc:
        response_code = getattr(exc, "smtp_code", None)
        logger.warning(
            "SMTP delivery failed (%s, response code=%s)",
            type(exc).__name__,
            response_code,
        )
        raise RuntimeError("Unable to deliver the verification email") from exc


def _send_message(server, message: EmailMessage, username: str, password: str) -> None:
    if username:
        server.login(username, password)
    server.send_message(message)
