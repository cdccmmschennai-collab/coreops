"""HTTP client for the CoreOps Phase 2 ingestion endpoint.

    POST {COREOPS_API_URL}/integrations/easytime/punches/batch
    X-CoreOps-Connector-Token: <secret>

Mirrors ``client.py`` (the EasyTime side) in shape and in its two refusals:

1. **Never log a secret.** The token is written into a header dict and nowhere
   else - not the URL, not a query string, not an exception message, not a
   debug line. Response bodies pass through ``redaction.excerpt`` before they
   reach a log or an error.
2. **Never treat an unrecognised response as success.** A 200 whose body is not
   a batch result raises. Accepting it would advance the local cursor over
   punches that may never have been stored, and the connector would then be
   confidently, silently, permanently behind.

Status handling is the heart of this file, because "should I try again?" is a
different question for every failure:

    200/201   parse the counters and continue
    401/403   wrong token           -> stop, no retry (CoreOpsAuthError)
    404       wrong URL, or the backend has ingestion disabled
                                    -> stop, no retry (CoreOpsEndpointError)
    409       sync-batch row race   -> bounded retry (the backend's own
                                       ON CONFLICT path makes this transient)
    422       CoreOps refused the body -> stop, keep sanitized evidence
    429, 5xx  server-side pressure  -> bounded retry with jittered backoff
    timeout / connection failure    -> bounded retry with jittered backoff

An "endless retry" against a 401 or a 404 would hammer the VPS every five
minutes forever while achieving nothing, so those exit immediately and let the
process exit code raise the alarm instead.
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Any

import httpx

from config import PROVIDER, CoreOpsConfig
from exceptions import (
    CoreOpsAuthError,
    CoreOpsEndpointError,
    CoreOpsPayloadError,
    CoreOpsResponseError,
    CoreOpsServerError,
)
from redaction import excerpt
from schemas import NormalizedPunch

logger = logging.getLogger("easytime.coreops")

# The connector's machine credential. Deliberately NOT `Authorization`, so it
# can never be confused with (or fall back to) a user JWT, and never a query
# parameter, so it stays out of access logs and Referer headers.
CONNECTOR_TOKEN_HEADER = "X-CoreOps-Connector-Token"

_RETRYABLE_STATUS = frozenset({409, 429, 500, 502, 503, 504})

# Backoff schedule in seconds, indexed by the attempt that just failed:
# attempt 1 is immediate, then roughly 2s, 5s, 10s. Bounded and finite - the
# last entry repeats if COREOPS_RETRIES is raised above four.
_BACKOFF_SECONDS = (2.0, 5.0, 10.0)
_BACKOFF_JITTER = 0.25  # +/-25%, so a fleet of connectors does not resynchronize

# Keys a batch result must carry to be believed.
_RESULT_INT_FIELDS = ("received", "inserted", "duplicates", "unmapped", "invalid")


@dataclass(frozen=True)
class PunchBatch:
    """One POST body, already normalized and already chunked."""

    connector_id: str
    batch_key: str
    source_from_time: str
    source_to_time: str
    punches: list[NormalizedPunch]
    provider: str = PROVIDER

    def to_wire(self) -> dict:
        return {
            "provider": self.provider,
            "connector_id": self.connector_id,
            "batch_key": self.batch_key,
            "source_from_time": self.source_from_time,
            "source_to_time": self.source_to_time,
            "punches": [p.to_wire() for p in self.punches],
        }


@dataclass(frozen=True)
class BatchResult:
    """The Phase 2 response, parsed and validated.

    The backend's counting contract, which this connector relies on and the
    tests assert:

        inserted + duplicates + invalid == received
        unmapped is a SUBSET of inserted (inserted rows with employee_id NULL)
    """

    batch_id: str
    received: int
    inserted: int
    duplicates: int
    unmapped: int
    invalid: int
    status: str

    @property
    def counts_balance(self) -> bool:
        return self.inserted + self.duplicates + self.invalid == self.received

    def summary(self) -> str:
        return (
            f"batch_id={self.batch_id} received={self.received} "
            f"inserted={self.inserted} duplicates={self.duplicates} "
            f"unmapped={self.unmapped} invalid={self.invalid} status={self.status}"
        )


class CoreOpsClient:
    """One authenticated channel to one CoreOps deployment.

    Use as a context manager so the connection pool is closed::

        with CoreOpsClient(config) as coreops:
            result = coreops.send_batch(batch)
    """

    def __init__(
        self,
        config: CoreOpsConfig,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep=time.sleep,
    ) -> None:
        self._config = config
        # Injected so tests assert the backoff SCHEDULE without waiting for it.
        self._sleep = sleep
        self.last_attempts = 0
        self._client = httpx.Client(
            base_url=config.api_url,
            timeout=config.timeout_seconds,
            transport=transport,
            follow_redirects=False,
        )

    def __enter__(self) -> "CoreOpsClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # -- the only request this connector ever makes --------------------------
    def send_batch(self, batch: PunchBatch) -> BatchResult:
        """POST one batch and return the parsed counters.

        Raises, and never returns a partial result:
          CoreOpsAuthError      401/403 - fix the token
          CoreOpsEndpointError  404     - fix the URL, or enable ingestion
          CoreOpsPayloadError   422     - a contract bug; evidence is attached
          CoreOpsServerError    429/5xx/transport, after every retry
          CoreOpsResponseError  2xx with a body that is not a batch result
        """
        body = batch.to_wire()
        payload = self._post_with_retries(body, batch_key=batch.batch_key)
        result = parse_batch_result(payload)

        if not result.counts_balance:
            # The backend guarantees this arithmetic. If it does not hold, the
            # response did not come from the contract this connector was built
            # against, and its counters cannot be used to decide that a window
            # is safely stored.
            raise CoreOpsResponseError(
                "CoreOps returned counters that do not balance "
                f"(inserted+duplicates+invalid != received): {result.summary()}"
            )
        logger.info(
            "coreops.batch sent batch_key=%s punches=%d %s",
            batch.batch_key,
            len(batch.punches),
            result.summary(),
        )
        return result

    # -- internals -----------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        """The request headers. The ONLY place the token appears."""
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            CONNECTOR_TOKEN_HEADER: self._config.connector_token,
            "User-Agent": "CoreOps-EasyTime-Connector/3",
        }

    def _post_with_retries(self, body: dict, *, batch_key: str) -> Any:
        attempts = max(1, self._config.retries)
        self.last_attempts = 0
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            self.last_attempts = attempt
            try:
                response = self._client.post(
                    self._config.batch_url, json=body, headers=self._headers()
                )
            except httpx.TimeoutException:
                # The request may still have been APPLIED server-side. That is
                # safe: the retry carries the same batch key and the same
                # transaction ids, so the backend absorbs it as duplicates.
                last_error = CoreOpsServerError(
                    f"Timed out posting to CoreOps after "
                    f"{self._config.timeout_seconds}s (batch_key={batch_key})."
                )
            except httpx.TransportError as exc:
                last_error = CoreOpsServerError(
                    f"Could not reach CoreOps (batch_key={batch_key}): "
                    f"{type(exc).__name__}."
                )
            else:
                terminal = self._classify(response, batch_key=batch_key)
                if terminal is not None:
                    raise terminal
                if response.status_code in (200, 201):
                    return _parse_body(response)
                # Retryable status.
                last_error = CoreOpsServerError(
                    f"CoreOps returned HTTP {response.status_code} "
                    f"(batch_key={batch_key}): {excerpt(response.text)}"
                )

            if attempt < attempts:
                delay = backoff_delay(attempt)
                logger.warning(
                    "coreops.retry attempt=%d/%d batch_key=%s in=%.1fs reason=%s",
                    attempt,
                    attempts,
                    batch_key,
                    delay,
                    type(last_error).__name__,
                )
                self._sleep(delay)

        assert last_error is not None  # every loop exit sets it
        raise last_error

    def _classify(self, response: httpx.Response, *, batch_key: str) -> Exception | None:
        """Return the exception to raise NOW, or None to continue the loop.

        None means either "success" or "retryable"; the caller distinguishes
        them by status code. Everything returned from here is terminal.
        """
        status = response.status_code
        if status in (200, 201) or status in _RETRYABLE_STATUS:
            return None

        if status in (401, 403):
            # The message deliberately does not echo the response body: a
            # rejected-credentials body is exactly where a server might repeat
            # what it was sent.
            return CoreOpsAuthError(
                f"CoreOps rejected the connector token (HTTP {status}). Check that "
                "COREOPS_CONNECTOR_TOKEN matches EASYTIME_CONNECTOR_TOKEN on the "
                "CoreOps server. Not retried - the same token will fail again."
            )
        if status == 404:
            return CoreOpsEndpointError(
                f"CoreOps returned 404 for {self._config.batch_url}. Either "
                "COREOPS_API_URL is wrong, or the server has "
                "EASYTIME_INGESTION_ENABLED=false (a disabled deployment answers a "
                "bare 404 on purpose). Not retried."
            )
        if status == 422:
            return CoreOpsPayloadError(
                f"CoreOps refused the batch (HTTP 422, batch_key={batch_key}). This "
                "is a connector/contract bug, not a transient failure, so the run "
                "stops rather than resending the same body.",
                body_excerpt=excerpt(response.text),
            )
        return CoreOpsServerError(
            f"Unexpected HTTP {status} from CoreOps (batch_key={batch_key}): "
            f"{excerpt(response.text)}"
        )


def backoff_delay(attempt: int, *, rng: random.Random | None = None) -> float:
    """Seconds to wait after failed ``attempt`` (1-based).

    Roughly 2s, 5s, 10s, then 10s, with +/-25% jitter. Bounded on purpose: a
    connector that runs every five minutes gains nothing from a backoff longer
    than its own schedule - the next run simply picks the window up again.
    """
    base = _BACKOFF_SECONDS[min(attempt, len(_BACKOFF_SECONDS)) - 1]
    generator = rng or random
    return base * (1 + generator.uniform(-_BACKOFF_JITTER, _BACKOFF_JITTER))


def _parse_body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise CoreOpsResponseError(
            f"CoreOps returned HTTP {response.status_code} with a non-JSON body: "
            f"{excerpt(response.text)}"
        ) from exc


def parse_batch_result(payload: Any) -> BatchResult:
    """Validate a Phase 2 ``PunchBatchResult`` body into a ``BatchResult``.

    Strict by design. Every required key must be present, the five counters
    must be integers (``bool`` excluded - it is an ``int`` subclass in Python
    and would sail straight through a naive check), and none may be negative.
    Anything else raises rather than defaulting to zero: a silent zero would
    read as "nothing to do" and the cursor would move anyway.
    """
    if not isinstance(payload, dict):
        raise CoreOpsResponseError(
            f"CoreOps returned {type(payload).__name__}, expected a batch-result "
            f"object: {excerpt(payload)}"
        )

    batch_id = payload.get("batch_id")
    if not isinstance(batch_id, str) or not batch_id.strip():
        raise CoreOpsResponseError(
            f"CoreOps response has no usable batch_id: {excerpt(payload)}"
        )
    status = payload.get("status")
    if not isinstance(status, str) or not status.strip():
        raise CoreOpsResponseError(
            f"CoreOps response has no usable status: {excerpt(payload)}"
        )

    counts: dict[str, int] = {}
    for field_name in _RESULT_INT_FIELDS:
        value = payload.get(field_name)
        if isinstance(value, bool) or not isinstance(value, int):
            raise CoreOpsResponseError(
                f"CoreOps response field {field_name!r} is not an integer: "
                f"{excerpt(payload)}"
            )
        if value < 0:
            raise CoreOpsResponseError(
                f"CoreOps response field {field_name!r} is negative: {value}"
            )
        counts[field_name] = value

    return BatchResult(batch_id=batch_id.strip(), status=status.strip(), **counts)
