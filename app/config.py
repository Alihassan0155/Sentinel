from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    frontend_url: str = "http://localhost:3000"
    frontend_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    auth_cookie_secure: bool = False
    database_url: str
    gemini_api_key: str
    gemini_model: str = "gemini-2.5-flash-lite"
    embedding_model: str = "gemini-embedding-001"
    investigation_threshold: int = Field(default=70, ge=0, le=100)
    notification_cooldown_minutes: int = Field(default=180, ge=0)
    notification_timezone: str = "Asia/Karachi"
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str | None = None
    notification_email_to: str | None = None
    smtp_starttls: bool = True
    website_min_interval_seconds: float = Field(default=2.0, ge=0)
    gemini_min_interval_seconds: float = Field(default=1.0, ge=0)
    max_rate_wait_seconds: float = Field(default=10.0, ge=0)
    http_timeout_seconds: float = Field(default=20.0, gt=0)
    http_max_bytes: int = Field(default=2_000_000, ge=1000)
    http_retry_attempts: int = Field(default=3, ge=1, le=5)
    browser_timeout_ms: int = Field(default=15_000, ge=1000)
    gemini_timeout_ms: int = Field(default=30_000, ge=1000)
    check_job_max_attempts: int = Field(default=4, ge=1, le=10)
    worker_poll_seconds: int = Field(default=2, ge=1)
    worker_stale_minutes: int = Field(default=30, ge=1)

    @field_validator(
        "smtp_host", "smtp_from", "notification_email_to",
        "smtp_username", "smtp_password", mode="before",
    )
    @classmethod
    def empty_smtp_placeholders(cls, value):
        return None if isinstance(value, str) and value.strip() in {"", "..."} else value

    @field_validator("smtp_port", mode="before")
    @classmethod
    def default_smtp_port(cls, value):
        return 587 if isinstance(value, str) and value.strip() in {"", "..."} else value

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
