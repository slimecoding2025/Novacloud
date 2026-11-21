import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://novacloud:novacloud@localhost:5432/novacloud"
    )
    app_version: str = "0.1.0"


settings = Settings()
