from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# The backend package lives one level below BASE_DIR
BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR/".env", extra="ignore")

    database_url: str = "sqlite:///./neighborlend.db"
    jwt_secret: str = "neighborlend-super-secret-key-2026-prototype"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7
    upload_dir: str = "./uploads"
    public_base_url: str = "http://localhost:8000"
    ai_model_path: str = "./ai_service/best_model/best.pt"
    ai_confidence_threshold: float = 0.45
    mock_payments: bool = True
    cors_origins: str = "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173,http://127.0.0.1:5174"
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
