"""Connector error taxonomy.

One exception per failure *class*, because the sync loop (Phase 2) reacts
differently to each: an auth failure means re-authenticate, a transport failure
means retry with backoff, and a response-shape failure means the installed
EasyTime version does not match what the client assumes and a human must look
at it (retrying would loop forever).

No exception ever carries a token, password or Authorization header in its
message - see ``client._sanitize``.
"""
from __future__ import annotations


class EasyTimeError(Exception):
    """Base class for every EasyTime connector failure."""


class EasyTimeConfigError(EasyTimeError):
    """The connector .env is missing or contradictory (raised before any I/O)."""


class EasyTimeAuthError(EasyTimeError):
    """Authentication or token refresh was rejected (HTTP 401/403, bad creds).

    Not retryable with the same credentials.
    """


class EasyTimeTransportError(EasyTimeError):
    """Connection refused, DNS failure, TLS failure or timeout.

    Retryable: EasyTime Pro is a desktop service and is routinely restarted.
    """


class EasyTimeHTTPError(EasyTimeError):
    """Non-2xx response that is not an auth failure."""

    def __init__(self, status_code: int, url: str, body_excerpt: str = "") -> None:
        self.status_code = status_code
        self.url = url
        self.body_excerpt = body_excerpt
        super().__init__(f"HTTP {status_code} from {url}: {body_excerpt[:200]}")


class EasyTimeResponseError(EasyTimeError):
    """A 2xx response whose shape the connector does not recognise.

    This is the signal that the installed EasyTime Pro version differs from the
    one this client was written against. Do NOT retry - update the client after
    re-running ``probe.py``.
    """
