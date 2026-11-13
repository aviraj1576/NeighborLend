"""JWT configuration and authenticated API regressions; no private keys/network."""

import json
import os
import secrets
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from jose import jwt
from pydantic import SecretStr, ValidationError
from test_razorpay_escrow import flow as payment_flow

from app.config import Settings
from app.models import User
from app.services import auth
from app.services.razorpay_service import ProviderError, configured_provider

flow = payment_flow
FORMER_DEFAULT = "neighborlend-super-secret-key-2026-prototype"


def config(**changes):
    return Settings(_env_file=None, **changes)


@pytest.mark.parametrize("environment", ["development", "test", "production"])
@pytest.mark.parametrize("exposure", ["local", "public"])
def test_missing_key_fails_in_every_environment(monkeypatch, environment, exposure):
    monkeypatch.delenv("JWT_SECRET")
    assert Settings.model_fields["jwt_secret"].is_required()
    with pytest.raises(ValidationError, match="jwt_secret"):
        config(app_env=environment, deployment_exposure=exposure)


@pytest.mark.parametrize("environment", ["development", "test", "production"])
@pytest.mark.parametrize(
    "weak",
    [
        "",
        "short",
        "a" * 64,
        "0123456789" * 8,
        FORMER_DEFAULT,
        FORMER_DEFAULT.upper(),
        "change-me-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        "your-secret-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        "replace-me-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        "synthetic-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ\n",
    ],
)
def test_weak_keys_fail_without_disclosing_input(environment, weak):
    with pytest.raises(ValidationError) as error:
        config(app_env=environment, jwt_secret=weak)
    assert "JWT_SECRET" in str(error.value)
    if weak:
        assert weak not in str(error.value)


@pytest.mark.parametrize("environment", ["development", "test", "production"])
def test_strong_keys_are_masked_and_frozen(environment):
    key = secrets.token_urlsafe(48)
    settings = config(app_env=environment, jwt_secret=key)
    assert isinstance(settings.jwt_secret, SecretStr)
    assert key not in repr(settings)
    assert key not in str(settings)
    assert key not in settings.model_dump_json()
    with pytest.raises(ValidationError):
        settings.jwt_secret = SecretStr(FORMER_DEFAULT)
    with pytest.raises(ValidationError):
        settings.jwt_algorithm = "HS384"


@pytest.mark.parametrize("algorithm", ["none", "HS384", "RS256"])
def test_configuration_cannot_select_another_algorithm(algorithm):
    with pytest.raises(ValidationError):
        config(jwt_algorithm=algorithm)


def test_env_file_precedence_and_invalid_process_override(tmp_path, monkeypatch):
    first, second, process = (secrets.token_urlsafe(48) for _ in range(3))
    shared, backend = tmp_path / "shared.env", tmp_path / "backend.env"
    shared.write_text("JWT_SECRET=" + first, encoding="utf-8")
    backend.write_text("JWT_SECRET=" + second, encoding="utf-8")
    monkeypatch.delenv("JWT_SECRET")
    assert Settings(_env_file=(shared, backend)).jwt_secret.get_secret_value() == second
    monkeypatch.setenv("JWT_SECRET", process)
    assert Settings(_env_file=(shared, backend)).jwt_secret.get_secret_value() == process
    monkeypatch.setenv("JWT_SECRET", "")
    with pytest.raises(ValidationError):
        Settings(_env_file=(shared, backend))  # Never fall back past an invalid override.


def test_expired_rotated_and_former_default_tokens_are_rejected(monkeypatch):
    settings = config(jwt_secret=secrets.token_urlsafe(48))
    monkeypatch.setattr(auth, "settings", settings)
    current = settings.jwt_secret.get_secret_value()
    claims = {"sub": "application-user", "exp": datetime.utcnow() + timedelta(minutes=10)}
    assert (
        auth.decode_access_token(auth.create_access_token("application-user")) == "application-user"
    )
    for key in (FORMER_DEFAULT, secrets.token_urlsafe(48)):
        assert auth.decode_access_token(jwt.encode(claims, key, algorithm="HS256")) is None
    expired = {**claims, "exp": datetime.utcnow() - timedelta(minutes=1)}
    assert auth.decode_access_token(jwt.encode(expired, current, algorithm="HS256")) is None
    assert auth.decode_access_token(jwt.encode(claims, current, algorithm="HS384")) is None


@pytest.mark.parametrize(
    "claims",
    [
        {"sub": "user"},
        {"exp": 4102444800},
        {"sub": "", "exp": 4102444800},
        {"sub": " ", "exp": 4102444800},
        {"sub": 123, "exp": 4102444800},
        {"sub": "user", "exp": None},
        {"sub": "user", "exp": "invalid"},
        {"sub": "user", "exp": float("inf")},
    ],
)
def test_invalid_required_claims_are_rejected(claims):
    token = jwt.encode(claims, auth.settings.jwt_secret.get_secret_value(), algorithm="HS256")
    assert auth.decode_access_token(token) is None


@pytest.mark.parametrize("token", ["", "garbage", "a.b.c", None, 123])
def test_malformed_tokens_are_rejected(token):
    assert auth.decode_access_token(token) is None


def test_unsigned_token_is_rejected():
    import base64

    def segment(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()

    token = (
        segment({"alg": "none", "typ": "JWT"})
        + "."
        + segment({"sub": "user", "exp": 4102444800})
        + "."
    )
    assert auth.decode_access_token(token) is None


def test_invalid_key_rejected_before_application_import_side_effects(tmp_path):
    # Blank process value shadows the real .env; the private key is never used.
    upload = tmp_path / "must-not-exist"
    env = {
        **os.environ,
        "JWT_SECRET": "",
        "APP_ENV": "test",
        "AUTO_MIGRATE": "false",
        "DATABASE_URL": f"sqlite:///{(tmp_path / 'must-not-exist.db').as_posix()}",
        "UPLOAD_DIR": str(upload),
    }
    result = subprocess.run(
        [sys.executable, "-B", "-c", "import app.main"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "JWT_SECRET" in result.stderr
    assert not upload.exists() and not (tmp_path / "must-not-exist.db").exists()


def test_cached_provider_rechecks_key_policy_without_gateway_io():
    settings = config(payment_provider="disabled")
    # Simulate corruption that bypasses the frozen field, preserving the old
    # provider guard's defense in depth; ordinary assignment is rejected above.
    settings.__dict__["jwt_secret"] = SecretStr(FORMER_DEFAULT)
    with pytest.raises(ProviderError, match="private_strong_jwt_secret_required"):
        configured_provider(settings)


def test_login_me_payment_and_database_roles_remain_authoritative(flow):
    password = "Synthetic-login-password-42!"
    with flow["factory"]() as db:
        user = db.get(User, flow["ids"]["borrower"])
        user.password_hash = auth.hash_password(password)
        db.commit()
    client = flow["client"]
    login = client.post(
        "/api/auth/login", json={"username_or_email": "borrower", "password": password}
    )
    assert login.status_code == 200
    headers = {"Authorization": "Bearer " + login.json()["access_token"]}
    assert client.get("/api/auth/me", headers=headers).json()["id"] == flow["ids"]["borrower"]
    assert (
        client.get(f"/api/payments/bookings/{flow['booking']['id']}", headers=headers).status_code
        == 200
    )
    assert (
        client.post(
            "/api/payments/create-order",
            headers=headers,
            json={"booking_id": flow["booking"]["id"], "accepted_terms": True},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/auth/login", json={"username_or_email": "borrower", "password": "wrong"}
        ).status_code
        == 401
    )
    claims = {
        "sub": flow["ids"]["borrower"],
        "exp": datetime.utcnow() + timedelta(minutes=10),
        "is_admin": True,
    }
    forged_role = jwt.encode(claims, auth.settings.jwt_secret.get_secret_value(), algorithm="HS256")
    assert (
        client.get("/api/disputes", headers={"Authorization": "Bearer " + forged_role}).status_code
        == 403
    )
    for key in (FORMER_DEFAULT, secrets.token_urlsafe(48)):
        rejected = {"Authorization": "Bearer " + jwt.encode(claims, key, algorithm="HS256")}
        for path in (
            "/api/auth/me",
            f"/api/payments/bookings/{flow['booking']['id']}",
            "/api/disputes",
        ):
            response = client.get(path, headers=rejected)
            assert response.status_code == 401
            assert response.headers["www-authenticate"] == "Bearer"
    # Disabled/unverified/deleted accounts cannot authenticate with a valid JWT.
    with flow["factory"]() as db:
        db.get(User, flow["ids"]["borrower"]).is_verified = False
        db.commit()
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    missing = auth.create_access_token("nonexistent-application-user")
    assert (
        client.get("/api/auth/me", headers={"Authorization": "Bearer " + missing}).status_code
        == 401
    )


def test_email_otp_hmac_still_roundtrips():
    expected = auth.hash_email_otp("synthetic-user", "123456")
    assert auth.verify_email_otp("synthetic-user", "123456", expected)
    assert not auth.verify_email_otp("synthetic-user", "654321", expected)
    assert not auth.verify_email_otp("other-user", "123456", expected)
