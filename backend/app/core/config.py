"""Central application configuration, loaded from environment variables."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Recon OS"
    environment: str = "development"
    debug: bool = True

    # Database
    database_url: str = "sqlite:///./recon_os.db"

    # Auth
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12

    # Job execution: "inprocess" (zero infra, local dev) or "celery" (production)
    job_runner: str = "inprocess"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Storage: "local" or "s3"
    storage_backend: str = "local"
    storage_local_root: str = "./data/storage"
    s3_bucket: str = ""
    s3_endpoint_url: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "ap-south-1"

    # Uploads
    max_upload_mb: int = 200

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Default seed admin (dev convenience only)
    seed_admin_email: str = "admin@eroute.local"
    seed_admin_password: str = "ChangeMe123!"


@lru_cache
def get_settings() -> Settings:
    return Settings()
