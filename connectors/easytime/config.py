"""Connector configuration - administrator PC side only.

Every value is read from one environment file. Nothing in this file is ever
deployed to the CoreOps VPS: the EasyTime username/password belong on the
machine that can actually reach EasyTime Pro, and the VPS only ever sees
normalized punches over HTTPS (see docs/attendance/easytime-integration.md).

**Where that file lives** is resolved by ``resolve_env_path`` in one fixed
order, none of which is the caller's current working directory:

    1. an explicit ``env_path`` argument                      (tests, tooling)
    2. ``$COREOPS_CONNECTOR_ENV_FILE``                        (explicit override)
    3. ``<directory of this module>/.env``                    (source checkout,
                                                               and the Phase 1
                                                               probe folder)
    4. ``C:\\ProgramData\\CoreOps\\EasyTimeConnector\\config\\connector.env``
                                                              (installed)

An installed connector lands on 4: ``install_connector.ps1`` copies a whitelist
into ``C:\\Program Files\\CoreOps\\EasyTimeConnector\\`` and that whitelist has
no ``.env`` in it, so rule 3 cannot fire there. A source checkout and the Phase
1 probe folder both land on 3, which is why the probe workflow is unchanged.

Deliberately dependency-light: a frozen dataclass + python-dotenv, no pydantic.
The connector must install and run on a Windows admin PC with the smallest
possible dependency surface, and it shares no code with the backend.
"""
from __future__ import annotations

import os
import socket
from dataclasses import dataclass, replace
from pathlib import Path

from dotenv import load_dotenv

from exceptions import ConnectorConfigError, EasyTimeConfigError

CONNECTOR_DIR = Path(__file__).resolve().parent

# The source-checkout / Phase 1 probe location, next to the scripts themselves.
ENV_PATH = CONNECTOR_DIR / ".env"

# Where a real installation keeps its mutable files. ProgramData, not Program
# Files: the connector runs as a service account that must be able to write its
# state and logs, and Program Files is read-only for exactly that reason.
PROGRAM_DATA_DIR = Path(r"C:\ProgramData\CoreOps\EasyTimeConnector")

# The installed configuration file. Named connector.env rather than .env so it
# is visible in Explorer, obviously ours, and impossible to confuse with the
# probe's .env sitting in C:\CoreOps-EasyTime-Probe.
INSTALLED_CONFIG_FILENAME = "connector.env"

# Escape hatch: point the connector at a specific file. A PATH is not a secret,
# so this is safe to pass on a command line or set in a scheduled task; the
# credentials still only ever live inside the file it names.
ENV_FILE_OVERRIDE_VAR = "COREOPS_CONNECTOR_ENV_FILE"

# Relocate the whole mutable tree (config, data, logs) in one move. Exported by
# ``run_sync.ps1 -DataRoot`` so the wrapper and the Python process cannot end up
# reporting two different state files. It sets the DEFAULT root only:
# SYNC_STATE_PATH / SYNC_LOG_DIR / SYNC_LOCK_PATH in the configuration file
# still win, because those are the administrator's explicit choice.
DATA_ROOT_OVERRIDE_VAR = "COREOPS_CONNECTOR_DATA_ROOT"

# Development/test fallback, used whenever ProgramData does not exist (any
# non-Windows machine, and any checkout that has not been installed).
LOCAL_DATA_DIR = CONNECTOR_DIR / "data"
LOCAL_LOG_DIR = CONNECTOR_DIR / "logs"

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


def program_data_dir() -> Path:
    """The mutable root: ``C:\\ProgramData\\CoreOps\\EasyTimeConnector``.

    Computed on every call rather than pinned at import time, so
    ``$COREOPS_CONNECTOR_DATA_ROOT`` and a test that repoints
    ``config.PROGRAM_DATA_DIR`` both take effect everywhere it is derived from.
    """
    raw = (os.getenv(DATA_ROOT_OVERRIDE_VAR) or "").strip()
    return Path(raw).expanduser() if raw else PROGRAM_DATA_DIR


def installed_config_dir() -> Path:
    """``C:\\ProgramData\\CoreOps\\EasyTimeConnector\\config``."""
    return program_data_dir() / "config"


def installed_config_path() -> Path:
    """The one configuration file an installed connector reads."""
    return installed_config_dir() / INSTALLED_CONFIG_FILENAME


def resolve_env_path(env_path: Path | None = None) -> tuple[Path, str]:
    """Decide which environment file to read, and say why.

    Returns ``(path, source)`` where ``source`` is a short label used in error
    messages so the admin never has to guess which of the four rules fired. The
    path returned may not exist - existence is the caller's decision, because
    ``--status`` is allowed to run without a finished configuration.

    Nothing here consults the current working directory. Every candidate is
    either passed in, named in an environment variable, or derived from the
    location of this module, so ``run_sync.ps1`` resolves the same file whether
    it is started from Program Files, from Task Scheduler, or from C:\\.
    """
    if env_path is not None:
        return Path(env_path), "explicit path"

    override = (os.getenv(ENV_FILE_OVERRIDE_VAR) or "").strip()
    if override:
        return Path(override).expanduser(), f"${ENV_FILE_OVERRIDE_VAR}"

    # A .env next to this module means a source checkout or the Phase 1 probe
    # folder. Checked before ProgramData so installing the connector on the
    # admin PC does not quietly repoint the probe at the connector's config.
    if ENV_PATH.exists():
        return ENV_PATH, "source checkout (.env next to the scripts)"

    return installed_config_path(), "installed (ProgramData)"


def _missing_config_message(path: Path, source: str) -> str:
    """The one error an admin is most likely to meet. Make it actionable.

    Names the file, how it was chosen, and the exact command that creates it.
    Carries no value read from any configuration file, so it cannot leak one.
    """
    return (
        f"Configuration file not found: {path}\n"
        f"  chosen by: {source}\n"
        "  On an installed admin PC, create it from the shipped example and "
        "type the credentials in yourself:\n"
        f'    copy "{installed_config_dir()}\\{INSTALLED_CONFIG_FILENAME}.example" '
        f'"{installed_config_path()}"\n'
        f'    notepad "{installed_config_path()}"\n'
        "  In a source checkout, copy .env.example to .env next to the scripts "
        "instead (never commit the result)."
    )


def load_config(env_path: Path | None = None, *, require_credentials: bool = True) -> EasyTimeConfig:
    """Read the connector environment file into an ``EasyTimeConfig``.

    ``require_credentials=False`` is used by ``probe.py --check-config`` so the
    admin can validate the file layout before the integration account exists.
    """
    path, source = resolve_env_path(env_path)
    explicitly_named = env_path is not None or source.startswith("$")

    if path.exists():
        load_dotenv(path, override=False)
    elif require_credentials or (explicitly_named and env_path is None):
        # An override variable that names a file which is not there is a typo,
        # not a half-finished install: fail even in the read-only modes rather
        # than silently reading nothing.
        raise EasyTimeConfigError(_missing_config_message(path, source))

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


# ===========================================================================
# Phase 3 - the CoreOps side, the sync cadence and the local file layout.
#
# Kept in the SAME .env and the same dataclass style as the EasyTime settings
# above; a second configuration mechanism on a Windows admin PC is a second
# thing to get wrong. Nothing here is ever written back to the file, and no
# secret is ever carried in a redacted() view.
# ===========================================================================

# The backend's own limit (backend/app/modules/biometric/constants.py
# MAX_BATCH_SIZE). A larger SYNC_BATCH_SIZE would be rejected as a 422 by every
# POST, so it is refused at load time instead of at 03:00 on a Sunday.
COREOPS_MAX_BATCH_SIZE = 1000

# Path of the ingestion endpoint, relative to COREOPS_API_URL.
COREOPS_PUNCH_BATCH_PATH = "/integrations/easytime/punches/batch"

# The provider slug the backend accepts. Not configurable: the endpoint is
# provider-specific and rejects any other value with a 422.
PROVIDER = "easytime"

# Ceiling on any single fetch window. Protects against a very old cursor, a
# typo'd --from-date, and an operator who means "last week" and types last year.
DEFAULT_MAX_RANGE_DAYS = 31


@dataclass(frozen=True)
class CoreOpsConfig:
    """How to reach the CoreOps ingestion endpoint."""

    api_url: str
    connector_token: str
    connector_id: str
    timeout_seconds: float = 30.0
    retries: int = 4
    batch_size: int = 500

    @property
    def batch_url(self) -> str:
        """Absolute URL of the ingestion endpoint.

        The token is NEVER placed in this URL, or in any query string: URLs end
        up in access logs, proxy logs and Referer headers. It travels only in
        the X-CoreOps-Connector-Token header.
        """
        return f"{self.api_url}{COREOPS_PUNCH_BATCH_PATH}"

    def redacted(self) -> dict:
        """Log-safe view. The token is not masked by length - it is absent."""
        return {
            "api_url": self.api_url,
            "connector_id": self.connector_id,
            "connector_token": "***" if self.connector_token else "(unset)",
            "timeout_seconds": self.timeout_seconds,
            "retries": self.retries,
            "batch_size": self.batch_size,
        }


@dataclass(frozen=True)
class SyncConfig:
    """Cadence, window sizing and where this PC keeps its files."""

    lookback_minutes: int = 15
    reconciliation_days: int = 7
    first_run_lookback_hours: int = 24
    max_range_days: int = DEFAULT_MAX_RANGE_DAYS
    state_path: Path = LOCAL_DATA_DIR / "state.db"
    log_dir: Path = LOCAL_LOG_DIR
    lock_path: Path = LOCAL_DATA_DIR / "sync.lock"

    def redacted(self) -> dict:
        return {
            "lookback_minutes": self.lookback_minutes,
            "reconciliation_days": self.reconciliation_days,
            "first_run_lookback_hours": self.first_run_lookback_hours,
            "max_range_days": self.max_range_days,
            "state_path": str(self.state_path),
            "log_dir": str(self.log_dir),
            "lock_path": str(self.lock_path),
        }


@dataclass(frozen=True)
class ConnectorConfig:
    """Everything one sync run needs, in one object."""

    easytime: EasyTimeConfig
    coreops: CoreOpsConfig
    sync: SyncConfig

    def redacted(self) -> dict:
        return {
            "easytime": self.easytime.redacted(),
            "coreops": self.coreops.redacted(),
            "sync": self.sync.redacted(),
        }


def _default_data_dir() -> Path:
    """ProgramData on an installed machine, ./data in a checkout.

    Existence, not platform, is the test: an installed connector has had
    ``install_connector.ps1`` run, and a developer machine has not.
    """
    root = program_data_dir()
    return root / "data" if root.exists() else LOCAL_DATA_DIR


def _default_log_dir() -> Path:
    root = program_data_dir()
    return root / "logs" if root.exists() else LOCAL_LOG_DIR


def _env_path(name: str, default: Path) -> Path:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return Path(raw.strip()).expanduser()


def _default_connector_id() -> str:
    """A stable per-machine identity, used when CONNECTOR_ID is not pinned.

    The hostname is a reasonable default because the connector is tied to the
    one PC that can reach EasyTime. It is still worth pinning explicitly: the
    id appears on every `biometric_sync_batches` row, and a PC rename would
    otherwise silently split one connector's history into two.
    """
    try:
        host = socket.gethostname().strip()
    except OSError:  # pragma: no cover - gethostname does not realistically fail
        host = ""
    return (host or "easytime-connector")[:100]


def load_coreops_config(*, require_token: bool = True) -> CoreOpsConfig:
    """Read the CoreOps half of the connector .env.

    Assumes ``load_dotenv`` has already run (``load_connector_config`` does it).
    Fails CLOSED: a missing URL or token stops the run before any punch is
    fetched, rather than producing a batch with nowhere to go.
    """
    api_url = (os.getenv("COREOPS_API_URL") or "").strip().rstrip("/")
    token = os.getenv("COREOPS_CONNECTOR_TOKEN") or ""
    connector_id = (os.getenv("CONNECTOR_ID") or "").strip() or _default_connector_id()

    if require_token and not api_url:
        raise ConnectorConfigError(
            "COREOPS_API_URL is required (for example "
            "https://coreops.cdccmms.com/api/v1)."
        )
    if api_url and not api_url.startswith(("http://", "https://")):
        raise ConnectorConfigError(
            f"COREOPS_API_URL must start with http:// or https://; got {api_url!r}."
        )
    if require_token and not token:
        raise ConnectorConfigError(
            "COREOPS_CONNECTOR_TOKEN is required. It must match "
            "EASYTIME_CONNECTOR_TOKEN in the CoreOps VPS .env. Generate one with: "
            'python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )
    if len(connector_id) > 100:
        raise ConnectorConfigError(
            "CONNECTOR_ID must be 100 characters or fewer (the backend column is "
            "VARCHAR(100))."
        )

    batch_size = _env_int("SYNC_BATCH_SIZE", 500)
    if not 1 <= batch_size <= COREOPS_MAX_BATCH_SIZE:
        raise ConnectorConfigError(
            f"SYNC_BATCH_SIZE must be between 1 and {COREOPS_MAX_BATCH_SIZE} "
            f"(the backend rejects a larger batch outright); got {batch_size}."
        )
    retries = _env_int("COREOPS_RETRIES", 4)
    if not 1 <= retries <= 10:
        raise ConnectorConfigError(f"COREOPS_RETRIES must be between 1 and 10; got {retries}.")
    timeout = _env_float("COREOPS_TIMEOUT_SECONDS", 30.0)
    if timeout <= 0:
        raise ConnectorConfigError(f"COREOPS_TIMEOUT_SECONDS must be positive; got {timeout}.")

    return CoreOpsConfig(
        api_url=api_url,
        connector_token=token,
        connector_id=connector_id,
        timeout_seconds=timeout,
        retries=retries,
        batch_size=batch_size,
    )


def load_sync_config() -> SyncConfig:
    """Read the cadence and file-layout half of the connector .env."""
    lookback = _env_int("SYNC_LOOKBACK_MINUTES", 15)
    if lookback < 0:
        raise ConnectorConfigError(
            f"SYNC_LOOKBACK_MINUTES must be zero or greater; got {lookback}."
        )
    reconciliation_days = _env_int("SYNC_RECONCILIATION_DAYS", 7)
    if not 1 <= reconciliation_days <= 90:
        raise ConnectorConfigError(
            f"SYNC_RECONCILIATION_DAYS must be between 1 and 90; got {reconciliation_days}."
        )
    first_run_hours = _env_int("SYNC_FIRST_RUN_LOOKBACK_HOURS", 24)
    if not 1 <= first_run_hours <= 24 * 90:
        raise ConnectorConfigError(
            "SYNC_FIRST_RUN_LOOKBACK_HOURS must be between 1 and 2160 (90 days); "
            f"got {first_run_hours}."
        )
    max_range_days = _env_int("SYNC_MAX_RANGE_DAYS", DEFAULT_MAX_RANGE_DAYS)
    if not 1 <= max_range_days <= 366:
        raise ConnectorConfigError(
            f"SYNC_MAX_RANGE_DAYS must be between 1 and 366; got {max_range_days}."
        )
    if reconciliation_days > max_range_days:
        raise ConnectorConfigError(
            f"SYNC_RECONCILIATION_DAYS ({reconciliation_days}) exceeds "
            f"SYNC_MAX_RANGE_DAYS ({max_range_days}); the reconciliation pass could "
            "never run."
        )

    data_dir = _default_data_dir()
    state_path = _env_path("SYNC_STATE_PATH", data_dir / "state.db")
    return SyncConfig(
        lookback_minutes=lookback,
        reconciliation_days=reconciliation_days,
        first_run_lookback_hours=first_run_hours,
        max_range_days=max_range_days,
        state_path=state_path,
        log_dir=_env_path("SYNC_LOG_DIR", _default_log_dir()),
        # Defaults NEXT TO the state file, so relocating state with
        # SYNC_STATE_PATH relocates the lock with it and two connectors pointed
        # at different state files cannot block each other.
        lock_path=_env_path("SYNC_LOCK_PATH", state_path.parent / "sync.lock"),
    )


def load_connector_config(
    env_path: Path | None = None,
    *,
    require_credentials: bool = True,
) -> ConnectorConfig:
    """Load the complete Phase 3 configuration from one .env.

    ``require_credentials=False`` mirrors ``load_config``: it lets
    ``sync.py --status`` read the local state on a PC whose .env is not filled
    in yet, without pretending the connector could actually run.
    """
    easytime = load_config(env_path, require_credentials=require_credentials)
    return ConnectorConfig(
        easytime=easytime,
        coreops=load_coreops_config(require_token=require_credentials),
        sync=load_sync_config(),
    )
