"""Application settings, loaded from environment (.env).

All configuration lives here — no module hardcodes connection strings, ports, or
the product name. `PRODUCT_NAME` is the single brand identifier (Naming Decision
Record, D-001); nothing else names the product.
"""
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_SECRET_DEFAULT = "change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Runtime
    ENV: str = "local"
    API_V1_PREFIX: str = "/api/v1"
    PRODUCT_NAME: str = "CoreOps"

    # Security (consumed from V1 — Authentication)
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Datastores
    DATABASE_URL: str = "postgresql+psycopg://wms:wms@localhost:5433/wms"
    REDIS_URL: str = "redis://localhost:6381/0"
    CELERY_BROKER_URL: str = "redis://localhost:6381/1"

    # HTTP
    BACKEND_PORT: int = 8100
    CORS_ORIGINS: str = "http://localhost:3100"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @model_validator(mode="after")
    def _guard_secret_key(self) -> "Settings":
        # Outside local, a strong, non-default SECRET_KEY is mandatory (F6).
        if self.ENV != "local":
            if self.SECRET_KEY == _INSECURE_SECRET_DEFAULT or len(self.SECRET_KEY) < 32:
                raise ValueError(
                    "SECRET_KEY must be set to a strong value (>=32 chars) when ENV is not 'local'."
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
