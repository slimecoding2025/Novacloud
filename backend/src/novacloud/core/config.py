import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    environment: str = field(default_factory=lambda: _env("NOVACLOUD_ENV", "development"))
    database_url: str = field(default_factory=lambda: _env(
        "DATABASE_URL", "postgresql+psycopg://novacloud:novacloud@localhost:5432/novacloud"))
    secret_key: str = field(default_factory=lambda: _env("NOVACLOUD_SECRET_KEY", ""))
    session_ttl_seconds: int = field(default_factory=lambda: int(_env("SESSION_TTL_SECONDS", "28800")))
    cookie_secure: bool = field(default_factory=lambda: _env("COOKIE_SECURE", "false") == "true")
    storage_root: str = field(default_factory=lambda: _env("STORAGE_ROOT", "./data/objects"))
    max_object_bytes: int = field(default_factory=lambda: int(_env("MAX_OBJECT_BYTES", str(10 * 1024 * 1024))))
    org_storage_quota_bytes: int = field(default_factory=lambda: int(_env("ORG_STORAGE_QUOTA_BYTES", str(1024**3))))
    max_instances_per_org: int = field(default_factory=lambda: int(_env("MAX_INSTANCES_PER_ORG", "20")))
    max_body_bytes: int = field(default_factory=lambda: int(_env("MAX_BODY_BYTES", str(11 * 1024 * 1024))))
    compute_provider: str = field(default_factory=lambda: _env("COMPUTE_PROVIDER", "runner"))
    runner_url: str = field(default_factory=lambda: _env("RUNNER_URL", "http://runner:8100"))
    runner_token: str = field(default_factory=lambda: _env("RUNNER_TOKEN", ""))
    login_rate_per_minute: int = field(default_factory=lambda: int(_env("LOGIN_RATE_PER_MINUTE", "10")))
    api_rate_per_minute: int = field(default_factory=lambda: int(_env("API_RATE_PER_MINUTE", "300")))
    registration_enabled: bool = field(default_factory=lambda: _env("REGISTRATION_ENABLED", "true") == "true")
    metrics_token: str = field(default_factory=lambda: _env("METRICS_TOKEN", ""))
    app_version: str = "0.2.0"

    def validate(self) -> None:
        """Fail fast on unsafe production configuration."""
        if self.environment == "production":
            if len(self.secret_key) < 32:
                raise ValueError("NOVACLOUD_SECRET_KEY must be at least 32 characters in production")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production")
            if self.compute_provider == "fake":
                raise ValueError("fake compute provider is not allowed in production")
