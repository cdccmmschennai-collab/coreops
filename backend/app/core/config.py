"""Application settings, loaded from environment (.env).

All configuration lives here — no module hardcodes connection strings, ports, or
the product name. `PRODUCT_NAME` is the single brand identifier (Naming Decision
Record, D-001); nothing else names the product.
"""
from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_SECRET_DEFAULT = "change-me-in-production"
_MIN_SECRET_LENGTH = 32
# Only these environments may run with the insecure dev default secret.
_DEV_ENVS = frozenset({"local", "test"})
_ALLOWED_ENVS = frozenset({"local", "test", "staging", "production"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Runtime
    # Fail-closed default: an unset or mistyped ENV is treated as production,
    # so the SECRET_KEY guard below applies unless ENV is explicitly local/test.
    ENV: str = "production"
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

    @field_validator("ENV")
    @classmethod
    def _validate_env(cls, value: str) -> str:
        if value not in _ALLOWED_ENVS:
            raise ValueError(
                f"ENV must be one of {sorted(_ALLOWED_ENVS)}; got {value!r}."
            )
        return value

    @model_validator(mode="after")
    def _guard_secret_key(self) -> "Settings":
        # Fail closed: only dev/test envs may use the insecure default secret.
        if self.ENV not in _DEV_ENVS:
            if (
                self.SECRET_KEY == _INSECURE_SECRET_DEFAULT
                or len(self.SECRET_KEY) < _MIN_SECRET_LENGTH
            ):
                raise ValueError(
                    f"SECRET_KEY must be a strong, non-default value "
                    f"(>= {_MIN_SECRET_LENGTH} chars) when ENV is {self.ENV!r}."
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
