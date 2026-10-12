import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings supplied by the environment, never by HTTP requests."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["local", "preview", "production"] = "local"
    database_url: str
    session_secret: SecretStr
    web_origin: str = "http://localhost:3000"
    session_ttl_hours: int = 168
    upload_max_bytes: int = 5 * 1024 * 1024
    upload_temp_dir: Path = Path(tempfile.gettempdir()) / "resume-job-matcher"
    generated_document_dir: Path = Path(tempfile.gettempdir()) / "resume-job-matcher" / "exports"
    mail_provider: Literal["disabled", "qq_smtp"] = "disabled"
    mail_from: str | None = None
    mail_smtp_host: str = "smtp.qq.com"
    mail_smtp_port: int = 465
    mail_smtp_username: str | None = None
    mail_smtp_authorization_code: SecretStr | None = None
    email_verification_ttl_hours: int = 24
    password_reset_ttl_minutes: int = 30
    llm_provider: Literal["disabled", "openai_compatible"] = "disabled"
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: SecretStr | None = None
    llm_timeout_seconds: float = 30.0
    llm_max_output_tokens: int = 2048

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must use the postgresql+psycopg scheme")
        return value

    @field_validator("session_secret")
    @classmethod
    def validate_session_secret(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if len(secret) < 32 or secret.startswith("replace-with-"):
            raise ValueError("SESSION_SECRET must be a unique value of at least 32 characters")
        return value

    @field_validator("session_ttl_hours")
    @classmethod
    def validate_session_ttl(cls, value: int) -> int:
        if not 1 <= value <= 24 * 30:
            raise ValueError("SESSION_TTL_HOURS must be between 1 and 720")
        return value

    @field_validator("upload_max_bytes")
    @classmethod
    def validate_upload_max_bytes(cls, value: int) -> int:
        if not 1 <= value <= 10 * 1024 * 1024:
            raise ValueError("UPLOAD_MAX_BYTES must be between 1 byte and 10 MiB")
        return value

    @model_validator(mode="after")
    def validate_production_origin(self) -> "Settings":
        if self.app_env == "production" and not self.web_origin.startswith("https://"):
            raise ValueError("WEB_ORIGIN must use HTTPS in production")
        if self.app_env == "production" and self.mail_provider == "disabled":
            raise ValueError("MAIL_PROVIDER must be configured in production")
        if self.mail_provider == "qq_smtp":
            if (
                not self.mail_from
                or not self.mail_smtp_username
                or not self.mail_smtp_authorization_code
            ):
                raise ValueError(
                    "QQ SMTP requires MAIL_FROM, MAIL_SMTP_USERNAME and authorization code"
                )
            if not 1 <= self.mail_smtp_port <= 65535:
                raise ValueError("MAIL_SMTP_PORT must be a valid port")
        if not 1 <= self.email_verification_ttl_hours <= 72:
            raise ValueError("EMAIL_VERIFICATION_TTL_HOURS must be between 1 and 72")
        if not 5 <= self.password_reset_ttl_minutes <= 120:
            raise ValueError("PASSWORD_RESET_TTL_MINUTES must be between 5 and 120")
        if self.llm_provider == "openai_compatible":
            if not self.llm_base_url or not self.llm_model:
                raise ValueError(
                    "LLM_BASE_URL and LLM_MODEL are required when LLM_PROVIDER is openai_compatible"
                )
            if not self.llm_base_url.startswith(("http://", "https://")):
                raise ValueError("LLM_BASE_URL must be an http(s) URL")
            if not 1.0 <= self.llm_timeout_seconds <= 300.0:
                raise ValueError("LLM_TIMEOUT_SECONDS must be between 1 and 300")
            if not 1 <= self.llm_max_output_tokens <= 32768:
                raise ValueError("LLM_MAX_OUTPUT_TOKENS must be between 1 and 32768")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
