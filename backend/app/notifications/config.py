"""SMTP / email configuration, loaded from environment.

Self-contained so the notification layer stays reusable and decoupled from the
core app settings. No credentials are ever hardcoded — everything comes from the
same ``.env`` the rest of the backend uses.

Environment variables
---------------------
  SMTP_HOST        SMTP server hostname (required to actually send)
  SMTP_PORT        SMTP server port (default 587)
  SMTP_USERNAME    login username (optional; omit for open relays)
  SMTP_PASSWORD    login password (optional)
  SMTP_FROM        From: address (defaults to SMTP_USERNAME when unset)
  SMTP_FROM_NAME   From: display name (default "CoreOps")
  SMTP_USE_TLS     STARTTLS after connect (default true)
  SMTP_USE_SSL     implicit TLS on connect, e.g. port 465 (default false)
  SMTP_TIMEOUT     socket timeout in seconds (default 30)
  EMAIL_ENABLED    master switch; when false, sends are logged and skipped
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class EmailSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_FROM_NAME: str = "CoreOps"
    SMTP_USE_TLS: bool = True
    SMTP_USE_SSL: bool = False
    SMTP_TIMEOUT: int = 30
    # Master switch. Off by default so a misconfigured deploy can never surprise
    # real inboxes; deployment turns it on explicitly.
    EMAIL_ENABLED: bool = False

    @property
    def from_address(self) -> str:
        """Effective From: address (falls back to the login user)."""
        return self.SMTP_FROM or self.SMTP_USERNAME

    @property
    def is_configured(self) -> bool:
        """True when enough is set to attempt a real send."""
        return bool(self.SMTP_HOST and self.from_address)


@lru_cache
def get_email_settings() -> EmailSettings:
    return EmailSettings()
