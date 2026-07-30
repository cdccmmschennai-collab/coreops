"""Connector configuration - administrator PC side only.

Every value is read from ``connectors/easytime/.env`` (git-ignored). Nothing in
this file is ever deployed to the CoreOps VPS: the EasyTime username/password
belong on the machine that can actually reach EasyTime Pro, and the VPS only
ever sees normalized punches over HTTPS (see docs/attendance/easytime-integration.md).

Deliberately dependency-light: a frozen dataclass + python-dotenv, no pydantic.
The connector must install and run on a Windows admin PC with the smallest
possible dependency surface, and it shares no code with the backend.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

from dotenv import load_dotenv

from exceptions import EasyTimeConfigError

CONNECTOR_DIR = Path(__file__).resolve().parent
ENV_PATH = CONNECTOR_DIR / ".env"

# Authentication modes. Which one the installed version actually accepts is an
# OPEN QUESTION until probe.py confirms it - do not hard-code an assumption.
AUTH_MODE_JWT = "jwt"
AUTH_MODE_TOKEN = "token"
AUTH_MODES = frozenset({AUTH_MODE_JWT, AUTH_MODE_TOKEN})

# Default Authorization header scheme per mode. ZKTeco builds differ here
# (some want "JWT <t>", some "Token <t>", some bare "<t>"); overridable via
# EASYTIME_AUTH_HEADER_SCHEME once the probe reports which one works.
_DEFAULT_HEADER_SCHEME = {AUTH_MODE_JWT: "JWT", AUTH_MODE_TOKEN: "Token"}

# Candidate paths, most-likely first. probe.py --discover walks these; the
# confirmed one is then pinned in .env so the sync loop never guesses.
AUTH_PATH_CANDIDATES = {
    AUTH_MODE_JWT: (
        "/api/jwt-api-token-auth/",
        "/jwt-api-token-auth/",
    ),
    AUTH_MODE_TOKEN: (
        "/api/api-token-auth/",
        "/api-token-auth/",
    ),
}
REFRESH_PATH_CANDIDATES = ("/api/jwt-api-token-refresh/",)
TRANSACTIONS_PATH_CANDIDATES = (
    "/iclock/api/transactions/",
    "/api/transactions/",
    "/att/api/transactionReport/",
)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise EasyTimeConfigError(f"{name} must be an integer; got {raw!r}.") from exc


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise EasyTimeConfigError(f"{name} must be a number; got {raw!r}.") from exc


@dataclass(frozen=True)
class EasyTimeConfig:
    """Everything needed to talk to EasyTime Pro on this PC."""

    base_url: str
    username: str
    password: str
    auth_mode: str = AUTH_MODE_JWT
    auth_header_scheme: str = ""
    auth_path: str = ""
    refresh_path: str = ""
    transactions_path: str = ""
    verify_ssl: bool = False
    timeout_seconds: float = 30.0
    retries: int = 3
    page_size: int = 100
    timezone: str = "Asia/Kolkata"

    # -- derived ------------------------------------------------------------
    @property
    def header_scheme(self) -> str:
        """The Authorization prefix, e.g. "JWT". Empty string = bare token."""
        if self.auth_header_scheme:
            return "" if self.auth_header_scheme.lower() == "none" else self.auth_header_scheme
        return _DEFAULT_HEADER_SCHEME[self.auth_mode]

    @property
    def auth_paths(self) -> tuple[str, ...]:
        return (self.auth_path,) if self.auth_path else AUTH_PATH_CANDIDATES[self.auth_mode]

    @property
    def refresh_paths(self) -> tuple[str, ...]:
        return (self.refresh_path,) if self.refresh_path else REFRESH_PATH_CANDIDATES

    @property
    def transactions_paths(self) -> tuple[str, ...]:
        return (
            (self.transactions_path,)
            if self.transactions_path
            else TRANSACTIONS_PATH_CANDIDATES
        )

    def redacted(self) -> dict:
        """Log-safe view. Password is never included, not even masked by length."""
        return {
            "base_url": self.base_url,
            "username": _mask(self.username),
            "password": "***",
            "auth_mode": self.auth_mode,
            "auth_header_scheme": self.header_scheme or "(bare)",
            "auth_path": self.auth_path or "(discover)",
            "transactions_path": self.transactions_path or "(discover)",
            "verify_ssl": self.verify_ssl,
            "timeout_seconds": self.timeout_seconds,
            "page_size": self.page_size,
            "timezone": self.timezone,
        }

    def with_paths(self, **paths: str) -> "EasyTimeConfig":
        """Return a copy with discovered paths pinned (used by probe.py)."""
        return replace(self, **paths)


def _mask(value: str) -> str:
    """Show only enough to recognise a value in a log line."""
    if not value:
        return ""
    if len(value) <= 2:
        return "*" * len(value)
    return f"{value[0]}{'*' * (len(value) - 2)}{value[-1]}"


def load_config(env_path: Path | None = None, *, require_credentials: bool = True) -> EasyTimeConfig:
    """Read the connector .env into an ``EasyTimeConfig``.

    ``require_credentials=False`` is used by ``probe.py --check-config`` so the
    admin can validate the file layout before the integration account exists.
    """
    path = env_path or ENV_PATH
    if path.exists():
        load_dotenv(path, override=False)
    elif require_credentials:
        raise EasyTimeConfigError(
            f"{path} not found. Copy .env.example to .env and fill it in "
            "(never commit the result)."
        )

    base_url = (os.getenv("EASYTIME_BASE_URL") or "").strip().rstrip("/")
    username = (os.getenv("EASYTIME_USERNAME") or "").strip()
    password = os.getenv("EASYTIME_PASSWORD") or ""
    auth_mode = (os.getenv("EASYTIME_AUTH_MODE") or AUTH_MODE_JWT).strip().lower()

    if auth_mode not in AUTH_MODES:
        raise EasyTimeConfigError(
            f"EASYTIME_AUTH_MODE must be one of {sorted(AUTH_MODES)}; got {auth_mode!r}."
        )
    if require_credentials:
        missing = [
            name
            for name, value in (
                ("EASYTIME_BASE_URL", base_url),
                ("EASYTIME_USERNAME", username),
                ("EASYTIME_PASSWORD", password),
            )
            if not value
        ]
        if missing:
            raise EasyTimeConfigError(
                "Missing required connector settings: " + ", ".join(missing)
            )
    if base_url and not base_url.startswith(("http://", "https://")):
        raise EasyTimeConfigError(
            f"EASYTIME_BASE_URL must start with http:// or https://; got {base_url!r}."
        )

    return EasyTimeConfig(
        base_url=base_url,
        username=username,
        password=password,
        auth_mode=auth_mode,
        auth_header_scheme=(os.getenv("EASYTIME_AUTH_HEADER_SCHEME") or "").strip(),
        auth_path=(os.getenv("EASYTIME_AUTH_PATH") or "").strip(),
        refresh_path=(os.getenv("EASYTIME_REFRESH_PATH") or "").strip(),
        transactions_path=(os.getenv("EASYTIME_TRANSACTIONS_PATH") or "").strip(),
        verify_ssl=_env_bool("EASYTIME_VERIFY_SSL", False),
        timeout_seconds=_env_float("EASYTIME_TIMEOUT_SECONDS", 30.0),
        retries=_env_int("EASYTIME_RETRIES", 3),
        page_size=_env_int("EASYTIME_PAGE_SIZE", 100),
        timezone=(os.getenv("TIMEZONE") or "Asia/Kolkata").strip(),
    )
