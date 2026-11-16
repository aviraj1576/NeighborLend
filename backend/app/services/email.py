import smtplib
import ssl
import logging
import base64
import urllib.parse
import urllib.request
from email.message import EmailMessage

from app.config import get_settings

logger = logging.getLogger(__name__)


def send_verification_code(recipient: str, code: str) -> None:
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_from_email:
        raise RuntimeError("Email delivery is not configured")

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
                timeout=15,
            ) as server:
                _send_message(server, message, settings.smtp_username, settings.smtp_password)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
                if settings.smtp_use_tls:
                    server.starttls(context=ssl.create_default_context())
                _send_message(server, message, settings.smtp_username, settings.smtp_password)
    except (OSError, smtplib.SMTPException) as exc:
        # Log enough to distinguish credential, sender, and connection failures
        # without exposing SMTP usernames, keys, sender addresses, or recipients.
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


def send_phone_verification_code(recipient: str, code: str) -> None:
    """Send a short-lived phone verification code through the configured Twilio account."""
    settings = get_settings()
    token = settings.twilio_auth_token.get_secret_value()
    if not (settings.twilio_account_sid and token and settings.twilio_from_number):
        raise RuntimeError("SMS verification is not configured")
    endpoint = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json"
    body = urllib.parse.urlencode({
        "To": recipient,
        "From": settings.twilio_from_number,
        "Body": f"Your NeighborLend verification code is {code}. It expires in 10 minutes.",
    }).encode()
    credentials = base64.b64encode(f"{settings.twilio_account_sid}:{token}".encode()).decode()
    request = urllib.request.Request(endpoint, data=body, headers={"Authorization": f"Basic {credentials}"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status >= 300:
                raise RuntimeError("SMS provider rejected the request")
    except Exception as exc:
        logger.warning("SMS delivery failed (%s)", type(exc).__name__)
        raise RuntimeError("Unable to deliver the verification SMS") from exc
