import ipaddress
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

BACKEND_ROOT = Path(__file__).resolve().parents[2]
LOCAL_SECRET_FILE = BACKEND_ROOT.parent / ".docker-secrets" / "postgres_password"
LOCAL_REDIS_SECRET_FILE = BACKEND_ROOT.parent / ".docker-secrets" / "redis_password"
LOCAL_DATABASE_URL = "postgresql+psycopg://{user}:{password}@127.0.0.1:55432/leadberry"
LOCAL_REDIS_URL = "redis://:{password}@127.0.0.1:6379/0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_environment: Literal["development", "test", "production"] = "development"
    database_url: SecretStr | None = None
    auth_database_url: SecretStr | None = None
    redis_url: SecretStr | None = None
    invitation_token_key: SecretStr | None = Field(None, min_length=32)
    session_hours: int = Field(12, ge=1, le=24)
    redis_max_connections: int = Field(12, ge=1, le=100)
    http_timeout_seconds: float = Field(20, ge=1, le=120)
    http_max_connections: int = Field(20, ge=1, le=200)
    marketplace_worker_concurrency: int = Field(8, ge=1, le=32)
    marketplace_org_concurrency: int = Field(2, ge=1, le=8)
    api_requests_per_minute: int = Field(120, ge=10, le=10000)
    api_rate_limit_buckets: int = Field(10000, ge=100, le=100000)
    api_max_inflight_requests: int = Field(100, ge=10, le=1000)
    api_max_request_bytes: int = Field(1_048_576, ge=1024, le=52_428_800)
    trusted_proxy_networks: list[str] = Field(
        default_factory=lambda: ["127.0.0.0/8", "::1/128"]
    )
    allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8000", "http://127.0.0.1:8000"])
    db_pool_size: int = Field(6, ge=1, le=30)
    db_pool_timeout_seconds: int = Field(5, ge=1, le=30)
    db_pool_recycle_seconds: int = Field(1800, ge=60, le=7200)
    export_concurrency: int = Field(2, ge=1, le=8)
    db_statement_timeout_ms: int = Field(10000, ge=100, le=120000)
    db_lock_timeout_ms: int = Field(2000, ge=100, le=30000)
    marketplace_public_key_file: Path | None = None

    @field_validator("trusted_proxy_networks")
    @classmethod
    def validate_proxy_networks(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            try:
                normalized.append(str(ipaddress.ip_network(value, strict=False)))
            except ValueError:
                raise ValueError("TRUSTED_PROXY_NETWORKS must contain IP networks") from None
        return normalized

    @field_validator("database_url", "auth_database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        try:
            url = make_url(value.get_secret_value())
        except ArgumentError:
            raise ValueError("DATABASE_URL must be a PostgreSQL psycopg URL") from None
        if url.drivername != "postgresql+psycopg" or not url.host or not url.database or not url.username:
            raise ValueError("DATABASE_URL must include postgresql+psycopg, host, user and database")
        # URL query arguments must not override role, tenant context, or timeouts.
        if set(url.query) - {"sslmode", "sslrootcert", "sslcert", "sslkey", "channel_binding"}:
            raise ValueError("DATABASE_URL contains unsupported connection parameters")
        return value

    @model_validator(mode="after")
    def validate_timeouts_and_transport(self) -> "Settings":
        if self.app_environment == "development" and self.database_url is None:
            # Local setup: derive both app roles from the secret created by Initialize-DockerSecrets.ps1.
            if not LOCAL_SECRET_FILE.is_file():
                raise ValueError("DATABASE_URL is not set and .docker-secrets/postgres_password is missing; run scripts\\Initialize-DockerSecrets.ps1")
            password = quote(LOCAL_SECRET_FILE.read_text(encoding="utf-8").strip(), safe="")
            self.database_url = SecretStr(LOCAL_DATABASE_URL.format(user="crm_api", password=password))
            if self.auth_database_url is None:
                self.auth_database_url = SecretStr(LOCAL_DATABASE_URL.format(user="crm_auth", password=password))
            if self.redis_url is None and LOCAL_REDIS_SECRET_FILE.is_file():
                redis_password = quote(LOCAL_REDIS_SECRET_FILE.read_text(encoding="utf-8").strip(), safe="")
                self.redis_url = SecretStr(LOCAL_REDIS_URL.format(password=redis_password))
        if self.database_url is None:
            raise ValueError("DATABASE_URL must be set outside development")
        if self.marketplace_org_concurrency > self.marketplace_worker_concurrency:
            raise ValueError(
                "MARKETPLACE_ORG_CONCURRENCY cannot exceed MARKETPLACE_WORKER_CONCURRENCY"
            )
        if self.db_lock_timeout_ms >= self.db_statement_timeout_ms:
            raise ValueError("DB_LOCK_TIMEOUT_MS must be below DB_STATEMENT_TIMEOUT_MS")
        if self.app_environment == "production":
            for value in (self.database_url, self.auth_database_url):
                if value is not None and make_url(value.get_secret_value()).query.get("sslmode") != "verify-full":
                    raise ValueError("Production database URLs require sslmode=verify-full")
            if any(not origin.startswith("https://") for origin in self.allowed_origins):
                raise ValueError("Production ALLOWED_ORIGINS must use HTTPS")
        if self.auth_database_url is not None:
            runtime = make_url(self.database_url.get_secret_value())
            identity = make_url(self.auth_database_url.get_secret_value())
            if (runtime.host, runtime.port, runtime.database) != (identity.host, identity.port, identity.database):
                raise ValueError("Identity and runtime database URLs must use the same database")
            if runtime.username == identity.username:
                raise ValueError("Identity and runtime database users must be distinct")
        return self
