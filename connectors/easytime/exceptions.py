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


# ---------------------------------------------------------------------------
# Phase 3: the CoreOps side, the local state store and the run lock.
#
# These are deliberately SEPARATE from the EasyTime classes above. "EasyTime is
# down" and "CoreOps rejected the payload" are different incidents with
# different owners and different exit codes (see exit_codes.py), and a single
# generic error class would collapse that distinction at exactly the moment an
# operator needs it.
# ---------------------------------------------------------------------------


class CoreOpsError(EasyTimeError):
    """Base class for every failure talking to the CoreOps ingestion API."""


class CoreOpsAuthError(CoreOpsError):
    """401 / 403 - the connector token is wrong, missing or revoked.

    NOT retryable: the same token will be rejected forever. Fix
    COREOPS_CONNECTOR_TOKEN (it must match EASYTIME_CONNECTOR_TOKEN on the VPS).
    """


class CoreOpsEndpointError(CoreOpsError):
    """404 - the ingestion endpoint is not there.

    Either COREOPS_API_URL is wrong, or the backend has
    ``EASYTIME_INGESTION_ENABLED=false`` (a disabled deployment deliberately
    answers a bare 404 rather than advertising that the route exists). NOT
    retryable - a human has to change something.
    """


class CoreOpsPayloadError(CoreOpsError):
    """422 - CoreOps refused the batch as a whole.

    A connector bug or a contract drift, not a transient condition. Retrying
    the identical body would fail identically, so the run stops and keeps the
    SANITIZED response excerpt as evidence.
    """

    def __init__(self, message: str, *, body_excerpt: str = "") -> None:
        self.body_excerpt = body_excerpt
        super().__init__(message)


class CoreOpsServerError(CoreOpsError):
    """5xx / 429 that survived every retry, or a transport failure.

    Retryable in principle - the connector already retried with bounded
    backoff and gave up. The window was NOT ingested and the cursor did not
    move, so the next scheduled run covers it again.
    """


class CoreOpsResponseError(CoreOpsError):
    """A 2xx whose body is not a batch result the connector can trust.

    Treated as a failure, never as success: silently accepting an unparseable
    body would advance the cursor over punches that may never have been stored.
    """


class ConnectorConfigError(EasyTimeConfigError):
    """A Phase 3 setting is missing or contradictory (CoreOps / sync / paths)."""


class ConnectorStateError(EasyTimeError):
    """The local SQLite state store is unreadable, corrupt or from the future.

    Never repaired automatically: deleting a cursor is a decision with
    consequences (a huge re-fetch), so the connector stops and says what to do.
    """


class RunLockUnavailable(EasyTimeError):
    """Another connector run holds the lock on this machine.

    Not an error condition in the usual sense - a 5-minute schedule overlapping
    one slow run is expected. The second invocation exits cleanly and quietly.
    """
