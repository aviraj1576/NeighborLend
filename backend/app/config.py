from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# The backend package lives one level below BASE_DIR
BACKEND_DIR = Path(__file__).resolve().parent.parent


def validate_jwt_secret(value: SecretStr) -> SecretStr:
    """Fail closed in every environment, including isolated tests.

    Length/diversity checks detect common configuration mistakes; operators must
    still generate the key privately using a cryptographically secure generator.
    Error text must never contain the supplied key.
    """
    secret = value.get_secret_value()
    if (
        len(secret.encode("utf-8")) < 32
        or len(set(secret)) < 12
        or any(character.isspace() for character in secret)
        or secret.casefold() == "neighborlend-super-secret-key-2026-prototype"
        or secret.casefold().startswith(
            (
                "change-me",
                "changeme",
                "your-",
                "your_",
                "replace-",
                "replace_",
                "example-",
                "dev-secret",
                "development-secret",
                "test-secret",
            )
        )
    ):
        raise ValueError(
            "JWT_SECRET must be a privately generated key of at least 32 bytes, "
            "with at least 12 distinct characters, no whitespace, and no default/placeholder value"
        )
    return value


class Settings(BaseSettings):
    # Absolute paths make local startup independent of the working directory.
    # Backend-only values override the shared file; process variables override both.
    model_config = SettingsConfigDict(
        env_file=(BASE_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    database_url: str = "sqlite:///./neighborlend.db"
    app_env: str = "development"
    # No fallback, even for APP_ENV=test. Tests inject a generated isolated key.
    jwt_secret: SecretStr = Field(repr=False, frozen=True)
    jwt_algorithm: Literal["HS256"] = Field(default="HS256", frozen=True)
    jwt_expire_minutes: int = 60 * 24 * 7
    upload_dir: str = "./uploads"
    public_base_url: str = "http://localhost:8000"
    ai_model_path: str = "./ai_service/best_model.pt"
    ai_confidence_threshold: float = 0.45
    mock_payments: bool = True
    # MOCK_PAYMENTS is deprecated and never grants payment authority.
    payment_provider: Literal["disabled", "mock", "razorpay_test"] = "disabled"
    payment_demo_mode: bool = False
    deployment_exposure: str = "local"
    auto_migrate: bool = False
    rental_evidence_dir: str = "./private-rental-evidence"
    razorpay_key_id: str = ""
    razorpay_key_secret: SecretStr = SecretStr("")
    razorpay_webhook_secret: SecretStr = SecretStr("")
    cors_origins: str = (
        "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173,http://127.0.0.1:5174"
    )
    admin_emails: str = "admin@neighborlend.com"
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    google_client_id: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True

    @field_validator("jwt_secret")
    @classmethod
    def require_private_jwt_secret(cls, value: SecretStr) -> SecretStr:
        return validate_jwt_secret(value)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def admin_email_list(self) -> list[str]:
        return [e.strip().lower() for e in self.admin_emails.split(",") if e.strip()]

    @property
    def upload_dir_abs(self) -> str:
        """
        Always returns an absolute path to the uploads directory, regardless
        of the working directory uvicorn/gunicorn is launched from.

        If upload_dir is already absolute, it is used as-is.
        If it is relative (e.g. './uploads'), it is resolved relative to the
        backend package root (the directory that contains app/) so that
        launching uvicorn from the project root, the backend dir, or anywhere
        else all produce the same resolved path.
        """
        p = Path(self.upload_dir)
        if p.is_absolute():
            return str(p)
        return str((BACKEND_DIR / self.upload_dir).resolve())

    @property
    def ai_model_path_abs(self) -> str:
        path = Path(self.ai_model_path)
        if path.is_absolute():
            return str(path)
        return str((BACKEND_DIR / path).resolve())


@lru_cache
def get_settings() -> Settings:
    return Settings()
