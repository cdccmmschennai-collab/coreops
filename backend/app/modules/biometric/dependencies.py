"""Connector authentication - a machine identity, entirely separate from users.

The office-side connector is NOT a person. It has no User row, no role, no
project scope and no session, so it must never authenticate with an employee or
project-manager JWT: a leaked connector secret would otherwise be a leaked user
account. It presents one shared secret in a dedicated header instead.

Rules enforced here:

* Off by default. While ``EASYTIME_INGESTION_ENABLED`` is false the route
  answers a bare 404 - the same response an unknown path gives - so a disabled
  deployment does not advertise that an ingestion endpoint exists.
* Fail closed. If ingestion is enabled but no token is configured, every request
  is rejected. (In staging/production ``Settings`` refuses to boot at all in
  that state; this is the second line of defence for local/test.)
* Constant-time comparison, so response timing cannot be used to recover the
  secret byte by byte.
* Dedicated header, never a query parameter - query strings end up in access
  logs, proxy logs, browser history and Referer headers.
* The supplied token is never logged, never echoed, and never written to an
  audit row. Failures return one generic message that does not distinguish
  "no token" from "wrong token".
"""
import secrets

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.modules.audit.constants import STATUS_FAILURE, AuditAction, EntityType
from app.modules.audit.service import record_audit
from app.modules.biometric.constants import CONNECTOR_TOKEN_HEADER
from app.shared.errors import AppError

# Generic, deliberately uninformative failures.
_DISABLED = AppError("not_found", "Not found.", 404)
_UNAUTHORIZED = AppError("unauthorized", "Not authenticated.", 401)


class ConnectorIdentity:
    """The authenticated connector. Carries no secret material."""

    __slots__ = ("provider",)

    def __init__(self, provider: str) -> None:
        self.provider = provider


def require_connector(
    x_coreops_connector_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> ConnectorIdentity:
    """Authenticate the office connector, or raise 404/401.

    FastAPI maps the ``x_coreops_connector_token`` parameter to the
    ``X-CoreOps-Connector-Token`` request header (see
    ``constants.CONNECTOR_TOKEN_HEADER``).
    """
    if not settings.EASYTIME_INGESTION_ENABLED:
        # Not enabled here: behave exactly like a route that does not exist.
        raise _DISABLED

    expected = settings.EASYTIME_CONNECTOR_TOKEN or ""
    supplied = x_coreops_connector_token or ""

    # An unconfigured token can never be matched, not even by sending "".
    if not expected or not secrets.compare_digest(supplied, expected):
        _audit_auth_failure(db, reason="missing" if not supplied else "invalid")
        raise _UNAUTHORIZED

    return ConnectorIdentity(provider="connector")


def _audit_auth_failure(db: Session, *, reason: str) -> None:
    """Record a rejected connector authentication.

    `reason` is a coarse slug ("missing" / "invalid") - never the supplied
    value, its length, or any prefix of it. `commit=True` because the caller
    raises immediately afterwards and the request transaction is discarded.

    Only reachable while ingestion is ENABLED, so a disabled deployment cannot
    be used to flood audit_logs with unauthenticated writes.
    """
    try:
        record_audit(
            db,
            action=AuditAction.BIOMETRIC_CONNECTOR_AUTH_FAILED,
            actor=None,
            actor_email=None,
            actor_role="connector",
            entity_type=EntityType.BIOMETRIC_SYNC_BATCH,
            entity_id=None,
            status=STATUS_FAILURE,
            details={"reason": reason, "header": CONNECTOR_TOKEN_HEADER},
            commit=True,
        )
    except Exception:  # pragma: no cover - auditing must never mask a 401
        db.rollback()
