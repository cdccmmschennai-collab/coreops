"""Biometric ingestion vocabulary - providers, batch statuses, limits, redaction.

Single source of truth shared by the models, the migration's CHECK constraints,
the service and the tests, so a status string is never spelled twice.

Phase 2 deliberately defines NO punch-state semantics. `raw_punch_state` is
stored verbatim; the live probe returned "0" for every observed punch and
`punch_state_display` was null, so IN/OUT remains unresolved
(docs/attendance/punch-state-mapping.md).
"""

# ── providers ───────────────────────────────────────────────────────────────
PROVIDER_EASYTIME = "easytime"

# Only providers listed here may be ingested. Adding one is a code change, not
# a payload the connector can choose freely.
SUPPORTED_PROVIDERS = frozenset({PROVIDER_EASYTIME})


# ── sync batch statuses ─────────────────────────────────────────────────────
BATCH_PROCESSING = "processing"
BATCH_COMPLETED = "completed"
BATCH_COMPLETED_WITH_ERRORS = "completed_with_errors"
BATCH_FAILED = "failed"

BATCH_STATUSES = (
    BATCH_PROCESSING,
    BATCH_COMPLETED,
    BATCH_COMPLETED_WITH_ERRORS,
    BATCH_FAILED,
)


# ── batch error codes (stored on biometric_sync_batches.error_code) ─────────
ERROR_ALL_RECORDS_INVALID = "all_records_invalid"
ERROR_STORAGE_FAILURE = "storage_failure"


# ── per-record rejection reasons (counted as `invalid`, never persisted as a
#    punch). Kept as short stable slugs so operations can grep them. ─────────
INVALID_MISSING_TRANSACTION_ID = "missing_external_transaction_id"
INVALID_MISSING_EMPLOYEE_CODE = "missing_employee_code"
INVALID_PUNCH_TIME = "invalid_punch_time"
INVALID_PUNCH_TIME_OUT_OF_RANGE = "punch_time_out_of_range"
INVALID_DUPLICATE_IN_BATCH = "duplicate_in_batch"


# ── size limits ─────────────────────────────────────────────────────────────
# One connector POST. 1000 punches ≈ a busy full day for a few hundred staff,
# and keeps the single INSERT statement and its JSONB payloads well inside
# comfortable request/statement sizes.
MAX_BATCH_SIZE = 1000

MAX_EXTERNAL_ID_LEN = 128
MAX_EMPLOYEE_CODE_LEN = 64
MAX_CONNECTOR_ID_LEN = 100
MAX_BATCH_KEY_LEN = 128
MAX_SHORT_FIELD_LEN = 100
MAX_STATE_FIELD_LEN = 50
MAX_TIMESTAMP_TEXT_LEN = 64

# raw_payload guard rails. A biometric transaction is a handful of scalars; a
# payload larger than this is either a different object or an attack.
MAX_RAW_PAYLOAD_KEYS = 40
MAX_RAW_PAYLOAD_VALUE_LEN = 500
MAX_RAW_PAYLOAD_CHARS = 4000

# Punch timestamps outside this window around "now" are rejected per-record:
# a device with a wildly wrong clock must not poison a date range.
MAX_PUNCH_AGE_DAYS = 400
MAX_PUNCH_FUTURE_DAYS = 2

# An unmapped ratio at or above this marks the batch for review (audit event).
UNMAPPED_ALERT_RATIO = 0.5
UNMAPPED_ALERT_MIN_RECORDS = 5


# ── redaction ───────────────────────────────────────────────────────────────
# Personally identifying / biometric material. CoreOps needs a code and a
# timestamp; names, photos, face and fingerprint templates are dropped before
# raw_payload is persisted. Mirrors connectors/easytime/schemas.py PII_FIELDS.
PII_KEYS = frozenset(
    {
        "first_name",
        "last_name",
        "name",
        "emp_name",
        "employee_name",
        "nickname",
        "photo",
        "picture",
        "avatar",
        "face",
        "face_template",
        "fingerprint",
        "finger_template",
        "template",
        "biophoto",
        "biodata",
        "vein",
        "iris",
        "palm",
        "email",
        "mobile",
        "phone",
        "address",
    }
)

# Secret-shaped keys. Never persisted, never logged, never echoed in an error.
SECRET_KEY_MARKERS = (
    "password",
    "passwd",
    "secret",
    "token",
    "jwt",
    "authorization",
    "auth",
    "api_key",
    "apikey",
    "credential",
    "session",
    "cookie",
)

# Reserved raw_payload key holding the vendor's original timestamp text, so the
# exact string EasyTime returned survives normalization (section 9).
RAW_PUNCH_TIME_TEXT_KEY = "_punch_time_text"
RAW_UPLOAD_TIME_TEXT_KEY = "_upload_time_text"

# The connector authenticates with this header. Deliberately NOT `Authorization`
# so a connector token can never be mistaken for (or fall back to) a user JWT,
# and never a query parameter so it stays out of access logs and referrers.
CONNECTOR_TOKEN_HEADER = "X-CoreOps-Connector-Token"
