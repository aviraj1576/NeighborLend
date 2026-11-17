import json
import unittest
from unittest.mock import MagicMock, patch

from app.services.email import _send_via_brevo_api, send_verification_code


class TestEmailDelivery(unittest.TestCase):
    def test_brevo_api_succeeds_over_https(self):
        settings = MagicMock()
        settings.smtp_host = "smtp-relay.brevo.com"
        settings.smtp_from_email = "verified@neighborlend.com"
        settings.smtp_password = "xsmtpsib-testkey"

        mock_resp = MagicMock()
        mock_resp.status = 201
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            result = _send_via_brevo_api("user@example.com", "123456", settings)
            self.assertTrue(result)
            self.assertTrue(mock_urlopen.called)

    def test_send_verification_code_uses_brevo_api_first(self):
        mock_settings = MagicMock()
        mock_settings.smtp_host = "smtp-relay.brevo.com"
        mock_settings.smtp_from_email = "verified@neighborlend.com"
        mock_settings.smtp_password = "xsmtpsib-testkey"

        with patch("app.services.email.get_settings", return_value=mock_settings), \
             patch("app.services.email._send_via_brevo_api", return_value=True) as mock_brevo, \
             patch("smtplib.SMTP") as mock_smtp:
            send_verification_code("user@example.com", "654321")
            self.assertTrue(mock_brevo.called)
            self.assertFalse(mock_smtp.called)

    def test_send_verification_code_falls_back_to_smtp_when_api_fails(self):
        mock_settings = MagicMock()
        mock_settings.smtp_host = "mail.generic-server.com"
        mock_settings.smtp_port = 587
        mock_settings.smtp_from_email = "noreply@generic-server.com"
        mock_settings.smtp_username = "user"
        mock_settings.smtp_password = "pass"
        mock_settings.smtp_use_tls = False

        mock_smtp_instance = MagicMock()
        with patch("app.services.email.get_settings", return_value=mock_settings), \
             patch("app.services.email._send_via_brevo_api", return_value=False), \
             patch("smtplib.SMTP", return_value=mock_smtp_instance) as mock_smtp:
            mock_smtp_instance.__enter__.return_value = mock_smtp_instance
            send_verification_code("user@example.com", "112233")
            self.assertTrue(mock_smtp.called)


if __name__ == "__main__":
    unittest.main()
