"""Offline private-key smoke check. Prints booleans only, never keys or tokens."""

import hashlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / ".test-tools"), str(ROOT)]


def main():
    private_env = ROOT / ".env"
    before = hashlib.sha256(private_env.read_bytes()).digest() if private_env.exists() else None
    try:
        # Imports may construct an engine but cannot connect to any database.
        with (
            patch("sqlalchemy.engine.Engine.connect", side_effect=AssertionError("Offline check")),
            patch(
                "urllib.request.OpenerDirector.open", side_effect=AssertionError("Offline check")
            ),
        ):
            from jose import jwt

            from app.config import get_settings
            from app.services.auth import create_access_token, decode_access_token

            settings = get_settings()
            token = create_access_token("isolated-jwt-configuration-check")
            assert decode_access_token(token) == "isolated-jwt-configuration-check"
            old = jwt.encode(
                {
                    "sub": "isolated-jwt-configuration-check",
                    "exp": datetime.utcnow() + timedelta(minutes=1),
                },
                "neighborlend-super-secret-key-2026-prototype",
                algorithm="HS256",
            )
            assert decode_access_token(old) is None
            key = settings.jwt_secret.get_secret_value()
            assert key not in repr(settings) and key not in settings.model_dump_json()
        after = hashlib.sha256(private_env.read_bytes()).digest() if private_env.exists() else None
        assert before == after
        print(
            json.dumps(
                {
                    "configuration_valid": True,
                    "token_round_trip": True,
                    "former_default_token_rejected": True,
                    "settings_key_redacted": True,
                    "backend_env_unchanged": True,
                    "external_requests": 0,
                }
            )
        )
        return 0
    except Exception as exc:
        # No exception text, settings, token or supplied key can enter output.
        print(json.dumps({"configuration_valid": False, "error_type": type(exc).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
