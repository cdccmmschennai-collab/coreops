"""CoreOps ingestion client - endpoint, header, retries and refusals.

Offline: ``httpx.MockTransport`` stands in for the CoreOps VPS. The theme of
this file is that "should I try again?" must be answered differently for every
failure class, and that a token must never reach a log, a URL or a message.
"""
from __future__ import annotations

import json
import logging
import random
from dataclasses import replace

import httpx
import pytest
from conftest import TEST_CONNECTOR_ID, TEST_CONNECTOR_TOKEN

from coreops_client import (
    CONNECTOR_TOKEN_HEADER,
    BatchResult,
    CoreOpsClient,
    PunchBatch,
    backoff_delay,
    parse_batch_result,
)
from exceptions import (
    CoreOpsAuthError,
    CoreOpsEndpointError,
    CoreOpsPayloadError,
    CoreOpsResponseError,
    CoreOpsServerError,
)
from schemas import NormalizedPunch


def punch(txn_id: str = "10432", code: str = "61") -> NormalizedPunch:
    return NormalizedPunch(
        provider="easytime",
        external_transaction_id=txn_id,
        employee_code=code,
        punch_time="2026-07-29T10:12:10+05:30",
        punch_state="0",
        punch_state_display=None,
        verify_type="1",
        terminal_serial_number="CDC-DEV-01",
        terminal_alias="F22/ID",
        source="1",
        upload_time="2026-07-30T07:02:00+05:30",
        raw_payload={"emp_code": code},
    )


def batch(*punches: NormalizedPunch, key: str = "et1-deadbeef") -> PunchBatch:
    return PunchBatch(
        connector_id=TEST_CONNECTOR_ID,
        batch_key=key,
        source_from_time="2026-07-29T00:00:00+05:30",
        source_to_time="2026-07-29T23:59:59+05:30",
        punches=list(punches) or [punch()],
    )


def ok_body(**overrides) -> dict:
    body = {
        "batch_id": "3f1a5b0e-0000-4000-8000-000000000001",
        "received": 1,
        "inserted": 1,
        "duplicates": 0,
        "unmapped": 0,
        "invalid": 0,
        "status": "completed",
    }
    body.update(overrides)
    return body


def build(config, handler, **kwargs) -> CoreOpsClient:
    # sleep is a no-op: the tests assert the retry SCHEDULE, not wall time.
    return CoreOpsClient(
        config, transport=httpx.MockTransport(handler), sleep=lambda _s: None, **kwargs
    )


class TestRequestShape:
    def test_posts_to_the_phase_2_endpoint(self, coreops_config):
        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            seen["method"] = request.method
            return httpx.Response(200, json=ok_body())

        with build(coreops_config, handler) as client:
            client.send_batch(batch())

        assert seen["method"] == "POST"
        assert seen["url"] == (
            "https://coreops.example.test/api/v1/integrations/easytime/punches/batch"
        )

    def test_sends_the_connector_token_header(self, coreops_config):
        seen = {}

        def handler(request):
            seen["token"] = request.headers.get(CONNECTOR_TOKEN_HEADER)
            seen["authorization"] = request.headers.get("Authorization")
            return httpx.Response(200, json=ok_body())

        with build(coreops_config, handler) as client:
            client.send_batch(batch())

        assert seen["token"] == TEST_CONNECTOR_TOKEN
        # Never Authorization: a connector token must not be able to travel any
        # path a user JWT travels.
        assert seen["authorization"] is None

    def test_token_is_never_in_the_url(self, coreops_config):
        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            return httpx.Response(200, json=ok_body())

        with build(coreops_config, handler) as client:
            client.send_batch(batch())

        assert TEST_CONNECTOR_TOKEN not in seen["url"]
        assert "?" not in seen["url"]

    def test_body_matches_the_phase_2_contract(self, coreops_config):
        captured = {}

        def capture(request):
            captured.update(json.loads(request.content))
            return httpx.Response(200, json=ok_body())

        with build(coreops_config, capture) as client:
            client.send_batch(batch(key="et1-abc"))

        assert captured["provider"] == "easytime"
        assert captured["connector_id"] == TEST_CONNECTOR_ID
        assert captured["batch_key"] == "et1-abc"
        assert captured["source_from_time"] == "2026-07-29T00:00:00+05:30"
        assert captured["source_to_time"] == "2026-07-29T23:59:59+05:30"
        assert len(captured["punches"]) == 1

    def test_raw_punch_state_and_null_display_are_sent_verbatim(self, coreops_config):
        """Section 17: "0" and null go over the wire exactly as observed."""
        captured = {}

        def capture(request):
            captured.update(json.loads(request.content))
            return httpx.Response(200, json=ok_body())

        with build(coreops_config, capture) as client:
            client.send_batch(batch())

        wire = captured["punches"][0]
        assert wire["raw_punch_state"] == "0"
        assert wire["punch_state_display"] is None
        assert "punch_state_display" in wire  # sent as null, not omitted
        assert wire["punch_time"] == "2026-07-29T10:12:10+05:30"


class TestSuccess:
    def test_parses_the_counters(self, coreops_config):
        def handler(request):
            return httpx.Response(
                200,
                json=ok_body(received=10, inserted=7, duplicates=2, unmapped=3, invalid=1),
            )

        with build(coreops_config, handler) as client:
            result = client.send_batch(batch())

        assert isinstance(result, BatchResult)
        assert (result.received, result.inserted, result.duplicates) == (10, 7, 2)
        assert result.unmapped == 3
        assert result.invalid == 1
        assert result.status == "completed"

    def test_201_is_also_success(self, coreops_config):
        def handler(request):
            return httpx.Response(201, json=ok_body())

        with build(coreops_config, handler) as client:
            assert client.send_batch(batch()).inserted == 1

    def test_unmapped_result_is_accepted_not_treated_as_a_failure(self, coreops_config):
        # An unmapped punch is STORED, just not attributed yet. The connector
        # must not treat it as a reason to stop or to withhold the cursor.
        def handler(request):
            return httpx.Response(
                200,
                json=ok_body(
                    received=5,
                    inserted=5,
                    unmapped=5,
                    status="completed_with_errors",
                ),
            )

        with build(coreops_config, handler) as client:
            result = client.send_batch(batch())

        assert result.unmapped == 5
        assert result.counts_balance


class TestNonRetryableFailures:
    @pytest.mark.parametrize("status", [401, 403])
    def test_auth_failure_is_not_retried(self, coreops_config, status):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(status, json={"detail": "Not authenticated."})

        with build(coreops_config, handler) as client:
            with pytest.raises(CoreOpsAuthError):
                client.send_batch(batch())

        assert calls["n"] == 1, "a wrong token will be wrong on every retry"

    def test_404_is_not_retried(self, coreops_config):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(404, json={"detail": "Not found."})

        with build(coreops_config, handler) as client:
            with pytest.raises(CoreOpsEndpointError) as exc:
                client.send_batch(batch())

        assert calls["n"] == 1
        # The message has to name BOTH causes: a disabled backend answers 404
        # deliberately, and looks identical to a wrong URL.
        assert "EASYTIME_INGESTION_ENABLED" in str(exc.value)

    def test_422_is_not_retried_and_keeps_evidence(self, coreops_config):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(
                422,
                json={"detail": [{"loc": ["body", "punches", 0, "punch_time"], "msg": "too long"}]},
            )

        with build(coreops_config, handler) as client:
            with pytest.raises(CoreOpsPayloadError) as exc:
                client.send_batch(batch())

        assert calls["n"] == 1
        assert "punch_time" in exc.value.body_excerpt

    def test_unexpected_4xx_is_not_retried(self, coreops_config):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(418, text="teapot")

        with build(coreops_config, handler) as client:
            with pytest.raises(CoreOpsServerError):
                client.send_batch(batch())

        assert calls["n"] == 1


class TestRetryableFailures:
    def test_429_is_retried(self, coreops_config):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            if calls["n"] < 3:
                return httpx.Response(429, text="slow down")
            return httpx.Response(200, json=ok_body())

        with build(coreops_config, handler) as client:
            assert client.send_batch(batch()).inserted == 1

        assert calls["n"] == 3

    @pytest.mark.parametrize("status", [500, 502, 503, 504])
    def test_5xx_is_retried(self, coreops_config, status):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(status, text="upstream trouble")
            return httpx.Response(200, json=ok_body())

        with build(coreops_config, handler) as client:
            assert client.send_batch(batch()).inserted == 1

        assert calls["n"] == 2

    def test_409_is_retried(self, coreops_config):
        # The backend's _resolve_batch race path returns 409; it is transient.
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(409, json={"detail": "Could not resolve the sync batch."})
            return httpx.Response(200, json=ok_body())

        with build(coreops_config, handler) as client:
            assert client.send_batch(batch()).received == 1

        assert calls["n"] == 2

    def test_timeout_is_retried(self, coreops_config):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            if calls["n"] == 1:
                raise httpx.ReadTimeout("timed out", request=request)
            return httpx.Response(200, json=ok_body())

        with build(coreops_config, handler) as client:
            assert client.send_batch(batch()).inserted == 1

        assert calls["n"] == 2

    def test_connection_failure_is_retried(self, coreops_config):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            if calls["n"] == 1:
                raise httpx.ConnectError("refused", request=request)
            return httpx.Response(200, json=ok_body())

        with build(coreops_config, handler) as client:
            assert client.send_batch(batch()).inserted == 1

    def test_retries_are_bounded(self, coreops_config):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(503, text="down")

        with build(coreops_config, handler) as client:
            with pytest.raises(CoreOpsServerError):
                client.send_batch(batch())

        # retries=3 in the fixture. Bounded, and it does not run forever.
        assert calls["n"] == 3

    def test_backoff_grows_and_carries_jitter(self):
        rng = random.Random(1)
        delays = [backoff_delay(n, rng=rng) for n in (1, 2, 3, 4)]

        assert 1.5 <= delays[0] <= 2.5
        assert 3.75 <= delays[1] <= 6.25
        assert 7.5 <= delays[2] <= 12.5
        # Attempt 4 repeats the last step rather than growing without bound.
        assert 7.5 <= delays[3] <= 12.5
        assert delays[0] < delays[1] < delays[2]


class TestMalformedResponses:
    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"batch_id": "abc"},
            {"batch_id": "", "received": 1, "inserted": 1, "duplicates": 0,
             "unmapped": 0, "invalid": 0, "status": "completed"},
            ok_body(received="1"),
            ok_body(inserted=True),
            ok_body(invalid=-1),
            ok_body(status=""),
            [1, 2, 3],
        ],
    )
    def test_unusable_body_raises_instead_of_counting_as_success(self, coreops_config, body):
        def handler(request):
            return httpx.Response(200, json=body)

        with build(coreops_config, handler) as client:
            with pytest.raises(CoreOpsResponseError):
                client.send_batch(batch())

    def test_non_json_body_raises(self, coreops_config):
        def handler(request):
            return httpx.Response(200, text="<html>proxy error</html>")

        with build(coreops_config, handler) as client:
            with pytest.raises(CoreOpsResponseError):
                client.send_batch(batch())

    def test_counters_that_do_not_balance_raise(self, coreops_config):
        # inserted + duplicates + invalid must equal received. If it does not,
        # this is not the contract the connector was built against, and its
        # numbers cannot be trusted to move a cursor.
        def handler(request):
            return httpx.Response(
                200, json=ok_body(received=10, inserted=1, duplicates=0, invalid=0)
            )

        with build(coreops_config, handler) as client:
            with pytest.raises(CoreOpsResponseError) as exc:
                client.send_batch(batch())

        assert "balance" in str(exc.value)

    def test_parse_batch_result_accepts_a_valid_body(self):
        result = parse_batch_result(ok_body(received=3, inserted=2, duplicates=1))

        assert result.received == 3
        assert result.counts_balance


class TestSecrets:
    def test_token_never_reaches_a_log_record(self, coreops_config, caplog):
        def handler(request):
            return httpx.Response(200, json=ok_body())

        with caplog.at_level(logging.DEBUG):
            with build(coreops_config, handler) as client:
                client.send_batch(batch())

        assert TEST_CONNECTOR_TOKEN not in caplog.text

    def test_token_never_reaches_a_log_record_on_failure(self, coreops_config, caplog):
        def handler(request):
            return httpx.Response(503, text="down")

        with caplog.at_level(logging.DEBUG):
            with build(coreops_config, handler) as client:
                with pytest.raises(CoreOpsServerError):
                    client.send_batch(batch())

        assert TEST_CONNECTOR_TOKEN not in caplog.text

    def test_a_server_that_echoes_a_secret_does_not_get_it_logged(self, coreops_config):
        def handler(request):
            return httpx.Response(422, json={"detail": "token=super-secret-value-here"})

        with build(coreops_config, handler) as client:
            with pytest.raises(CoreOpsPayloadError) as exc:
                client.send_batch(batch())

        assert "super-secret-value-here" not in exc.value.body_excerpt
        assert "super-secret-value-here" not in str(exc.value)

    def test_auth_error_message_does_not_echo_the_response_body(self, coreops_config):
        def handler(request):
            return httpx.Response(401, text="supplied token was aaaa-bbbb-cccc")

        with build(coreops_config, handler) as client:
            with pytest.raises(CoreOpsAuthError) as exc:
                client.send_batch(batch())

        assert "aaaa-bbbb-cccc" not in str(exc.value)

    def test_redacted_config_omits_the_token(self, coreops_config):
        redacted = coreops_config.redacted()

        assert redacted["connector_token"] == "***"
        assert TEST_CONNECTOR_TOKEN not in str(redacted)

    def test_a_blank_token_is_still_never_printed(self, coreops_config):
        blank = replace(coreops_config, connector_token="")

        assert blank.redacted()["connector_token"] == "(unset)"
