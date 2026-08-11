"""Contract tests against the REAL Phase 2 backend schemas.

Every other test in this suite asserts the connector against a fake CoreOps
that this repository also wrote - which proves the connector is self-consistent
and proves nothing about the actual endpoint. This file closes that gap by
importing ``backend/app/modules/biometric/schemas.py`` itself and validating the
connector's request body with the same Pydantic model FastAPI uses, plus the
backend's own limits from ``constants.py``.

It SKIPS when the backend is not importable. The connector's own virtualenv
deliberately has three packages in it and no Pydantic - it runs on an office PC,
not a build server. Run this file from the backend virtualenv (which has both on
the path) to get the coverage:

    backend\\.venv\\Scripts\\python -m pytest connectors/easytime/tests -q

A skip here is a gap in verification, never a pass.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from conftest import TEST_CONNECTOR_ID, live_transaction

pydantic = pytest.importorskip(
    "pydantic", reason="the backend schemas need pydantic; run from the backend venv"
)

BACKEND_DIR = Path(__file__).resolve().parents[3] / "backend"
if BACKEND_DIR.exists() and str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

biometric_schemas = pytest.importorskip(
    "app.modules.biometric.schemas",
    reason=f"backend package not importable from {BACKEND_DIR}",
)
biometric_constants = pytest.importorskip("app.modules.biometric.constants")

PunchBatchIn = biometric_schemas.PunchBatchIn
PunchIn = biometric_schemas.PunchIn
PunchBatchResult = biometric_schemas.PunchBatchResult

import mapper  # noqa: E402
from config import COREOPS_MAX_BATCH_SIZE, PROVIDER  # noqa: E402
from coreops_client import CONNECTOR_TOKEN_HEADER, PunchBatch, parse_batch_result  # noqa: E402
from schemas import RawTransaction  # noqa: E402

IST_NAME = "Asia/Kolkata"


def connector_batch(count: int = 3) -> PunchBatch:
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(IST_NAME)
    rows = [RawTransaction.parse(live_transaction(n)) for n in range(1, count + 1)]
    punches, rejected = mapper.normalize_all(rows, provider=PROVIDER, tz=tz)
    assert not rejected
    return PunchBatch(
        connector_id=TEST_CONNECTOR_ID,
        batch_key=mapper.batch_key(
            connector_id=TEST_CONNECTOR_ID,
            provider=PROVIDER,
            source_from="2026-07-29T00:00:00+05:30",
            source_to="2026-07-29T23:59:59+05:30",
            batch_number=1,
            external_transaction_ids=[p.external_transaction_id for p in punches],
        ),
        source_from_time="2026-07-29T00:00:00+05:30",
        source_to_time="2026-07-29T23:59:59+05:30",
        punches=punches,
    )


class TestRequestBody:
    def test_the_connector_body_validates_against_the_backend_model(self):
        body = connector_batch().to_wire()

        parsed = PunchBatchIn.model_validate(body)

        assert parsed.provider == "easytime"
        assert parsed.connector_id == TEST_CONNECTOR_ID
        assert len(parsed.punches) == 3

    def test_it_survives_a_json_round_trip(self):
        # The real path is JSON over the wire, not a Python dict.
        body = json.loads(json.dumps(connector_batch().to_wire()))

        assert len(PunchBatchIn.model_validate(body).punches) == 3

    def test_the_raw_state_and_null_display_arrive_as_the_backend_reads_them(self):
        parsed = PunchBatchIn.model_validate(connector_batch(1).to_wire())
        punch = parsed.punches[0]

        # The whole point of Phase 3 section 17.
        assert punch.raw_punch_state == "0"
        assert punch.punch_state_display is None

    def test_every_field_the_connector_sends_is_a_field_the_backend_declares(self):
        wire = connector_batch(1).to_wire()

        assert set(wire) <= set(PunchBatchIn.model_fields)
        # PunchIn's aliases mean the field NAME set is not identical; check the
        # backend accepts each key rather than assuming equality.
        punch_keys = set(wire["punches"][0])
        accepted = set(PunchIn.model_fields) | {"punch_state", "verification_type",
                                                "external_employee_code"}
        assert punch_keys <= accepted, punch_keys - accepted

    def test_the_timestamp_format_the_connector_emits_is_accepted(self):
        parsed = PunchBatchIn.model_validate(connector_batch(1).to_wire())

        assert parsed.punches[0].punch_time == "2026-07-29T10:12:10+05:30"
        # The backend parses per record with datetime.fromisoformat.
        from datetime import datetime

        assert datetime.fromisoformat(parsed.punches[0].punch_time).utcoffset() is not None


class TestLimits:
    def test_the_connector_batch_ceiling_matches_the_backend(self):
        assert COREOPS_MAX_BATCH_SIZE == biometric_constants.MAX_BATCH_SIZE

    def test_the_batch_key_fits_the_backend_column(self):
        key = connector_batch().batch_key

        assert len(key) <= biometric_constants.MAX_BATCH_KEY_LEN

    def test_the_connector_id_fits_the_backend_column(self):
        assert len(TEST_CONNECTOR_ID) <= biometric_constants.MAX_CONNECTOR_ID_LEN

    def test_the_provider_slug_matches(self):
        assert PROVIDER == biometric_constants.PROVIDER_EASYTIME
        assert PROVIDER in biometric_constants.SUPPORTED_PROVIDERS

    def test_the_header_name_matches(self):
        assert CONNECTOR_TOKEN_HEADER == biometric_constants.CONNECTOR_TOKEN_HEADER

    def test_a_batch_over_the_limit_is_rejected_by_the_backend_model(self):
        # Proof that the connector's own SYNC_BATCH_SIZE guard is not cosmetic.
        body = connector_batch(1).to_wire()
        body["punches"] = body["punches"] * (biometric_constants.MAX_BATCH_SIZE + 1)

        with pytest.raises(pydantic.ValidationError):
            PunchBatchIn.model_validate(body)


class TestResponseParsing:
    def test_the_connector_parses_a_real_PunchBatchResult(self):
        import uuid

        result = PunchBatchResult(
            batch_id=uuid.uuid4(),
            received=10,
            inserted=7,
            duplicates=2,
            unmapped=3,
            invalid=1,
            status="completed_with_errors",
        )
        # mode="json" is what FastAPI serializes, turning the UUID into a str.
        payload = result.model_dump(mode="json")

        parsed = parse_batch_result(payload)

        assert parsed.batch_id == str(result.batch_id)
        assert parsed.received == 10
        assert parsed.unmapped == 3
        assert parsed.counts_balance

    def test_the_counting_contract_the_connector_asserts_is_the_backend_s(self):
        """inserted + duplicates + invalid == received, unmapped is a subset.

        The connector refuses a response where this does not hold. That is only
        safe because the backend guarantees it - assert the docstring says so,
        so a future backend change that breaks the invariant is caught here
        rather than by the connector rejecting every live batch.
        """
        assert "inserted + duplicates + invalid == received" in PunchBatchResult.__doc__
