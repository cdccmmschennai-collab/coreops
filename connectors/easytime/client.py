"""HTTP client for EasyTime Pro's third-party API.

Responsibilities, and nothing else: authenticate, refresh, GET transactions,
follow pagination, retry transport failures, and hand back ``RawTransaction``
objects. No attendance rules, no session building, no database, no CoreOps.

Two things this client refuses to do, on purpose:

1. **Guess the punch-state meaning.** It returns the vendor code untouched.
2. **Log a secret.** Passwords and tokens never reach a log line, an exception
   message or a probe report - see ``_sanitize`` and the header handling.

The installed EasyTime version is not known in advance, so paths are candidate
lists (config.py) and the response shape is matched against the handful of
envelopes ZKTeco builds use. An unrecognised envelope raises
``EasyTimeResponseError`` rather than being coerced into something plausible.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from datetime import date, datetime
from typing import Any

import httpx

from config import AUTH_MODE_JWT, EasyTimeConfig
from exceptions import (
    EasyTimeAuthError,
    EasyTimeHTTPError,
    EasyTimeResponseError,
    EasyTimeTransportError,
)
from schemas import RawTransaction

logger = logging.getLogger("easytime.client")

# Query parameter names used by the transactions endpoint. Verified by probe.py
# against the live install; if a build uses different names the probe reports
# the mismatch instead of the client silently fetching an unfiltered page.
PARAM_START = "start_time"
PARAM_END = "end_time"
PARAM_EMP_CODE = "emp_code"
PARAM_PAGE = "page"
PARAM_PAGE_SIZE = "page_size"

# Keys that carry a token in an auth response, most-likely first.
_TOKEN_KEYS = ("token", "access", "access_token", "jwt")
# Keys that wrap the record list in a paginated response.
_LIST_KEYS = ("data", "results")

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_PAGES = 10_000  # hard stop; a malformed `next` must never loop forever


def _sanitize(value: Any) -> str:
    """Render a value for logging with anything token-shaped removed."""
    text = str(value)
    for marker in ("token", "password", "Authorization", "access"):
        if marker.lower() in text.lower():
            return f"<redacted:{marker}>"
    return text[:200]


class EasyTimeClient:
    """One authenticated session against one EasyTime Pro install.

    Use as a context manager so the underlying HTTP connection is closed::

        with EasyTimeClient(config) as client:
            client.authenticate()
            for txn in client.iter_transactions(start, end):
                ...
    """

    def __init__(self, config: EasyTimeConfig, *, transport: httpx.BaseTransport | None = None) -> None:
        self._config = config
        self._token: str | None = None
        self._refresh_token: str | None = None
        self._auth_path_used: str | None = None
        self._transactions_path_used: str | None = None
        # Per-fetch counters, reset at the start of every iter_transactions run.
        self.last_parse_errors: list[str] = []
        self.last_page_count = 0
        self.last_record_count = 0
        self._client = httpx.Client(
            base_url=config.base_url,
            timeout=config.timeout_seconds,
            verify=config.verify_ssl,
            transport=transport,
            follow_redirects=True,
        )

    # -- lifecycle ----------------------------------------------------------
    def __enter__(self) -> "EasyTimeClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    @property
    def is_authenticated(self) -> bool:
        return self._token is not None

    @property
    def auth_path_used(self) -> str | None:
        """The auth path that actually worked - pin it in .env afterwards."""
        return self._auth_path_used

    @property
    def transactions_path_used(self) -> str | None:
        return self._transactions_path_used

    # -- authentication -----------------------------------------------------
    def authenticate(self) -> str:
        """Obtain an access token, trying each configured candidate path.

        Returns the token (never logged). Raises ``EasyTimeAuthError`` when the
        credentials are rejected everywhere, ``EasyTimeResponseError`` when a
        path answers 200 with no recognisable token field.
        """
        payload = {"username": self._config.username, "password": self._config.password}
        last_error: Exception | None = None

        for path in self._config.auth_paths:
            try:
                response = self._request("POST", path, json=payload, authenticated=False)
            except EasyTimeHTTPError as exc:
                # 404 = wrong path for this build; keep trying. 400/401 = the
                # path exists and the credentials were refused.
                if exc.status_code in (401, 403):
                    raise EasyTimeAuthError(
                        f"EasyTime rejected the integration credentials at {path} "
                        f"(HTTP {exc.status_code})."
                    ) from exc
                last_error = exc
                continue

            token = _extract_token(response, _TOKEN_KEYS)
            if token is None:
                raise EasyTimeResponseError(
                    f"{path} returned HTTP 200 without a recognisable token field. "
                    f"Keys seen: {sorted(_as_dict(response).keys())}"
                )
            self._token = token
            self._refresh_token = _extract_token(response, ("refresh", "refresh_token"))
            self._auth_path_used = path
            logger.info("easytime.auth ok path=%s mode=%s", path, self._config.auth_mode)
            return token

        raise EasyTimeAuthError(
            "No EasyTime authentication endpoint responded successfully. Tried: "
            + ", ".join(self._config.auth_paths)
            + (f" (last error: {last_error})" if last_error else "")
        )

    def refresh(self) -> str:
        """Refresh the JWT. Falls back to a full re-authenticate when the build
        exposes no refresh endpoint (token mode never has one)."""
        if self._config.auth_mode != AUTH_MODE_JWT or not self._token:
            return self.authenticate()

        body = {"token": self._token}
        if self._refresh_token:
            body["refresh"] = self._refresh_token

        for path in self._config.refresh_paths:
            try:
                response = self._request("POST", path, json=body, authenticated=False)
            except (EasyTimeHTTPError, EasyTimeAuthError):
                continue
            token = _extract_token(response, _TOKEN_KEYS)
            if token:
                self._token = token
                logger.info("easytime.auth refreshed path=%s", path)
                return token
        logger.info("easytime.auth refresh unavailable - re-authenticating")
        return self.authenticate()

    # -- transactions -------------------------------------------------------
    def iter_transactions(
        self,
        start: datetime | date,
        end: datetime | date,
        *,
        employee_code: str | None = None,
        page_size: int | None = None,
    ) -> Iterator[RawTransaction]:
        """Yield every transaction in [start, end], following pagination.

        Records that cannot be parsed are counted in ``last_parse_errors`` and
        skipped - never silently dropped without a count, and never guessed at.
        """
        if not self.is_authenticated:
            self.authenticate()

        params: dict[str, Any] = {
            PARAM_START: _fmt_bound(start, end_of_day=False),
            PARAM_END: _fmt_bound(end, end_of_day=True),
            PARAM_PAGE_SIZE: page_size or self._config.page_size,
        }
        if employee_code:
            params[PARAM_EMP_CODE] = employee_code

        self.last_parse_errors: list[str] = []
        self.last_page_count = 0
        self.last_record_count = 0

        for path in self._config.transactions_paths:
            try:
                first = self._request("GET", path, params=params)
            except EasyTimeHTTPError as exc:
                if exc.status_code == 404:
                    continue  # wrong path for this build
                raise
            self._transactions_path_used = path
            yield from self._walk_pages(path, params, first)
            return

        raise EasyTimeResponseError(
            "No EasyTime transactions endpoint responded. Tried: "
            + ", ".join(self._config.transactions_paths)
        )

    def _walk_pages(self, path: str, params: dict, first: Any) -> Iterator[RawTransaction]:
        payload = first
        page = 1
        while True:
            self.last_page_count = page
            records = _extract_records(payload)
            for record in records:
                self.last_record_count += 1
                try:
                    yield RawTransaction.parse(record)
                except ValueError as exc:
                    self.last_parse_errors.append(str(exc))

            next_url = _next_url(payload)
            if not next_url or page >= _MAX_PAGES:
                return
            page += 1
            # `next` may be absolute (and may carry the admin PC's hostname);
            # httpx handles both absolute and relative here.
            payload = self._request("GET", next_url)

    def probe_path(self, method: str, path: str, **kwargs: Any) -> tuple[int, Any]:
        """Single raw call used by probe.py's discovery mode.

        Returns (status_code, parsed-body-or-text) WITHOUT raising for non-2xx,
        so the probe can report exactly which candidate paths exist.
        """
        try:
            response = self._client.request(method, path, headers=self._headers(), **kwargs)
        except httpx.TimeoutException as exc:
            raise EasyTimeTransportError(f"Timed out calling {path}: {exc}") from exc
        except httpx.TransportError as exc:
            raise EasyTimeTransportError(f"Could not reach {path}: {exc}") from exc
        return response.status_code, _parse_body(response)

    # -- internals ----------------------------------------------------------
    def _headers(self, *, authenticated: bool = True) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if authenticated and self._token:
            scheme = self._config.header_scheme
            headers["Authorization"] = f"{scheme} {self._token}".strip()
        return headers

    def _request(
        self,
        method: str,
        url: str,
        *,
        authenticated: bool = True,
        _retry_auth: bool = True,
        **kwargs: Any,
    ) -> Any:
        """One HTTP call with backoff on transport/5xx and one re-auth on 401."""
        attempts = max(1, self._config.retries)
        last_exc: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                response = self._client.request(
                    method, url, headers=self._headers(authenticated=authenticated), **kwargs
                )
            except httpx.TimeoutException:
                last_exc = EasyTimeTransportError(
                    f"Timed out calling {url} after {self._config.timeout_seconds}s."
                )
            except httpx.TransportError as exc:
                last_exc = EasyTimeTransportError(f"Could not reach {url}: {exc}")
            else:
                if response.status_code in (401, 403) and authenticated and _retry_auth:
                    # Token expired mid-run: refresh once, then replay.
                    logger.info("easytime.auth expired - refreshing and replaying %s", url)
                    self.refresh()
                    return self._request(
                        method, url, authenticated=authenticated, _retry_auth=False, **kwargs
                    )
                if response.status_code in _RETRYABLE_STATUS:
                    last_exc = EasyTimeHTTPError(
                        response.status_code, url, _sanitize(response.text)
                    )
                elif response.status_code >= 400:
                    raise EasyTimeHTTPError(
                        response.status_code, url, _sanitize(response.text)
                    )
                else:
                    return _parse_body(response)

            if attempt < attempts:
                backoff = min(2 ** (attempt - 1), 8)
                logger.warning(
                    "easytime.retry attempt=%d/%d url=%s in=%ss",
                    attempt,
                    attempts,
                    url,
                    backoff,
                )
                time.sleep(backoff)

        assert last_exc is not None  # loop always sets it before exhausting
        raise last_exc


# -- module helpers ---------------------------------------------------------
def _parse_body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def _as_dict(payload: Any) -> dict:
    return payload if isinstance(payload, dict) else {}


def _extract_token(payload: Any, keys: tuple[str, ...]) -> str | None:
    body = _as_dict(payload)
    for key in keys:
        value = body.get(key)
        if isinstance(value, str) and value:
            return value
    # Some builds nest under "data".
    nested = _as_dict(body.get("data"))
    for key in keys:
        value = nested.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _extract_records(payload: Any) -> list[dict]:
    """Pull the record list out of whichever envelope this build uses."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    body = _as_dict(payload)
    for key in _LIST_KEYS:
        value = body.get(key)
        if isinstance(value, list):
            return [r for r in value if isinstance(r, dict)]
        if isinstance(value, dict):  # {"data": {"results": [...]}}
            for inner in _LIST_KEYS:
                nested = value.get(inner)
                if isinstance(nested, list):
                    return [r for r in nested if isinstance(r, dict)]
    raise EasyTimeResponseError(
        "Unrecognised transactions envelope. Expected a list or an object with "
        f"'data'/'results'; got keys {sorted(body.keys())}."
    )


def _next_url(payload: Any) -> str | None:
    body = _as_dict(payload)
    value = body.get("next")
    if isinstance(value, str) and value:
        return value
    nested = _as_dict(body.get("data")).get("next")
    return nested if isinstance(nested, str) and nested else None


def _fmt_bound(value: datetime | date, *, end_of_day: bool) -> str:
    """Format an inclusive query bound as EasyTime expects (naive local text)."""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return f"{value.isoformat()} {'23:59:59' if end_of_day else '00:00:00'}"
