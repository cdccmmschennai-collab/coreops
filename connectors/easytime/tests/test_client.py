"""EasyTime client behaviour, entirely offline.

Covers the Phase 1 adapter test list: auth success/failure, refresh, expiry
mid-run, pagination, timeout, retryable server error, invalid response, missing
fields, and sanitized logging.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date

import httpx
import pytest
from conftest import transaction

from client import EasyTimeClient, _sanitize
from exceptions import (
    EasyTimeAuthError,
    EasyTimeHTTPError,
    EasyTimeResponseError,
    EasyTimeTransportError,
)


DAY = date(2026, 7, 28)


def build(config, handler) -> EasyTimeClient:
    return EasyTimeClient(config, transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def _no_backoff_sleep(monkeypatch):
    # The retry path sleeps between attempts; tests assert the behaviour, not
    # the wall-clock delay.
    monkeypatch.setattr("client.time.sleep", lambda _seconds: None)


class TestAuthentication:
    def test_returns_token_on_success(self, config):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/jwt-api-token-auth/"
            return httpx.Response(200, json={"token": "jwt-abc"})

        with build(config, handler) as client:
            assert client.authenticate() == "jwt-abc"
            assert client.is_authenticated
            assert client.auth_path_used == "/api/jwt-api-token-auth/"

    def test_rejected_credentials_raise_auth_error(self, config):
        def handler(request):
            return httpx.Response(401, json={"detail": "Invalid credentials"})

        with build(config, handler) as client:
            with pytest.raises(EasyTimeAuthError):
                client.authenticate()

    def test_walks_candidate_paths_until_one_answers(self, discovering_config):
        seen = []

        def handler(request):
            seen.append(request.url.path)
            if request.url.path == "/jwt-api-token-auth/":
                return httpx.Response(200, json={"token": "jwt-xyz"})
            return httpx.Response(404, text="not found")

        with build(discovering_config, handler) as client:
            assert client.authenticate() == "jwt-xyz"
            assert client.auth_path_used == "/jwt-api-token-auth/"
        assert seen == ["/api/jwt-api-token-auth/", "/jwt-api-token-auth/"]

    def test_200_without_a_token_field_is_a_response_error(self, config):
        # A build that answers 200 with an unexpected body must stop the run,
        # not carry on unauthenticated.
        def handler(request):
            return httpx.Response(200, json={"msg": "ok"})

        with build(config, handler) as client:
            with pytest.raises(EasyTimeResponseError):
                client.authenticate()

    def test_token_may_be_nested_under_data(self, config):
        def handler(request):
            return httpx.Response(200, json={"code": 0, "data": {"access": "nested-tok"}})

        with build(config, handler) as client:
            assert client.authenticate() == "nested-tok"

    def test_authorization_header_uses_the_configured_scheme(self, config):
        captured = {}

        def handler(request):
            if "token-auth" in request.url.path:
                return httpx.Response(200, json={"token": "jwt-abc"})
            captured["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, json={"data": []})

        with build(config, handler) as client:
            list(client.iter_transactions(DAY, DAY))
        assert captured["auth"] == "JWT jwt-abc"

    def test_bare_token_scheme(self, config):
        captured = {}
        cfg = replace(config, auth_header_scheme="none")

        def handler(request):
            if "token-auth" in request.url.path:
                return httpx.Response(200, json={"token": "plain"})
            captured["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, json={"data": []})

        with build(cfg, handler) as client:
            list(client.iter_transactions(DAY, DAY))
        assert captured["auth"] == "plain"


class TestRefresh:
    def test_refresh_endpoint_returns_a_new_token(self, config):
        def handler(request):
            if request.url.path.endswith("refresh/"):
                return httpx.Response(200, json={"token": "jwt-2"})
            return httpx.Response(200, json={"token": "jwt-1"})

        with build(config, handler) as client:
            client.authenticate()
            assert client.refresh() == "jwt-2"

    def test_falls_back_to_full_auth_when_refresh_is_absent(self, config):
        def handler(request):
            if request.url.path.endswith("refresh/"):
                return httpx.Response(404, text="no such endpoint")
            return httpx.Response(200, json={"token": "jwt-fresh"})

        with build(config, handler) as client:
            client.authenticate()
            assert client.refresh() == "jwt-fresh"

    def test_expiry_mid_fetch_triggers_one_reauth_and_a_replay(self, config):
        calls = {"auth": 0, "txn": 0}

        def handler(request):
            if "token-refresh" in request.url.path:
                calls["auth"] += 1
                return httpx.Response(200, json={"token": "tok-refreshed"})
            if "token-auth" in request.url.path:
                calls["auth"] += 1
                return httpx.Response(200, json={"token": f"tok-{calls['auth']}"})
            calls["txn"] += 1
            if calls["txn"] == 1:
                return httpx.Response(401, json={"detail": "token expired"})
            return httpx.Response(200, json={"data": [transaction(1)]})

        with build(config, handler) as client:
            rows = list(client.iter_transactions(DAY, DAY))

        assert len(rows) == 1
        assert calls["auth"] == 2  # initial + one refresh
        assert calls["txn"] == 2  # original + replay

    def test_persistent_401_does_not_loop_forever(self, config):
        def handler(request):
            if "token-auth" in request.url.path:
                return httpx.Response(200, json={"token": "tok"})
            return httpx.Response(401, json={"detail": "nope"})

        with build(config, handler) as client:
            with pytest.raises(EasyTimeHTTPError):
                list(client.iter_transactions(DAY, DAY))


class TestTransactions:
    def test_fetches_and_parses_records(self, config):
        def handler(request):
            if "token-auth" in request.url.path:
                return httpx.Response(200, json={"token": "tok"})
            return httpx.Response(200, json={"data": [transaction(1), transaction(2)]})

        with build(config, handler) as client:
            rows = list(client.iter_transactions(DAY, DAY))

        assert [r.external_transaction_id for r in rows] == ["1", "2"]
        assert client.last_record_count == 2
        assert client.last_parse_errors == []

    def test_sends_the_expected_query_bounds(self, config):
        captured = {}

        def handler(request):
            if "token-auth" in request.url.path:
                return httpx.Response(200, json={"token": "tok"})
            captured.update(dict(request.url.params))
            return httpx.Response(200, json={"data": []})

        with build(config, handler) as client:
            list(
                client.iter_transactions(
                    date(2026, 7, 28), date(2026, 7, 28), employee_code="EMP069"
                )
            )

        assert captured["start_time"] == "2026-07-28 00:00:00"
        assert captured["end_time"] == "2026-07-28 23:59:59"  # inclusive end
        assert captured["emp_code"] == "EMP069"

    def test_follows_pagination(self, config):
        def handler(request):
            if "token-auth" in request.url.path:
                return httpx.Response(200, json={"token": "tok"})
            page = request.url.params.get("page")
            if page is None:
                return httpx.Response(
                    200,
                    json={
                        "count": 3,
                        "next": "/iclock/api/transactions/?page=2",
                        "data": [transaction(1), transaction(2)],
                    },
                )
            return httpx.Response(200, json={"count": 3, "next": None, "data": [transaction(3)]})

        with build(config, handler) as client:
            rows = list(client.iter_transactions(DAY, DAY))

        assert [r.external_transaction_id for r in rows] == ["1", "2", "3"]
        assert client.last_page_count == 2

    def test_accepts_a_results_envelope(self, config):
        def handler(request):
            if "token-auth" in request.url.path:
                return httpx.Response(200, json={"token": "tok"})
            return httpx.Response(200, json={"results": [transaction(9)], "next": None})

        with build(config, handler) as client:
            rows = list(client.iter_transactions(DAY, DAY))

        assert len(rows) == 1

    def test_accepts_a_bare_list(self, config):
        def handler(request):
            if "token-auth" in request.url.path:
                return httpx.Response(200, json={"token": "tok"})
            return httpx.Response(200, json=[transaction(9)])

        with build(config, handler) as client:
            assert len(list(client.iter_transactions(DAY, DAY))) == 1

    def test_unknown_envelope_raises_instead_of_returning_nothing(self, config):
        # Returning zero punches silently would read as "nobody came to work".
        def handler(request):
            if "token-auth" in request.url.path:
                return httpx.Response(200, json={"token": "tok"})
            return httpx.Response(200, json={"payload": {"rows": []}})

        with build(config, handler) as client:
            with pytest.raises(EasyTimeResponseError):
                list(client.iter_transactions(DAY, DAY))

    def test_unparseable_record_is_counted_not_dropped_silently(self, config):
        def handler(request):
            if "token-auth" in request.url.path:
                return httpx.Response(200, json={"token": "tok"})
            broken = transaction(2)
            del broken["emp_code"]
            return httpx.Response(200, json={"data": [transaction(1), broken]})

        with build(config, handler) as client:
            rows = list(client.iter_transactions(DAY, DAY))

        assert len(rows) == 1
        assert len(client.last_parse_errors) == 1
        assert client.last_record_count == 2

    def test_order_is_preserved_as_returned(self, config):
        # Ordering is the session engine's job (Phase 3); the client must not
        # reorder or dedupe on its own.
        def handler(request):
            if "token-auth" in request.url.path:
                return httpx.Response(200, json={"token": "tok"})
            return httpx.Response(
                200,
                json={
                    "data": [
                        transaction(2, punch_time="2026-07-28 17:00:00", punch_state="1"),
                        transaction(1, punch_time="2026-07-28 09:30:00"),
                    ]
                },
            )

        with build(config, handler) as client:
            rows = list(client.iter_transactions(DAY, DAY))

        assert [r.external_transaction_id for r in rows] == ["2", "1"]


class TestResilience:
    def test_retries_a_500_then_succeeds(self, config):
        calls = {"n": 0}

        def handler(request):
            if "token-auth" in request.url.path:
                return httpx.Response(200, json={"token": "tok"})
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(503, text="restarting")
            return httpx.Response(200, json={"data": [transaction(1)]})

        with build(config, handler) as client:
            rows = list(client.iter_transactions(DAY, DAY))

        assert len(rows) == 1
        assert calls["n"] == 2

    def test_gives_up_after_configured_retries(self, config):
        def handler(request):
            if "token-auth" in request.url.path:
                return httpx.Response(200, json={"token": "tok"})
            return httpx.Response(500, text="boom")

        with build(config, handler) as client:
            with pytest.raises(EasyTimeHTTPError) as exc:
                list(client.iter_transactions(DAY, DAY))
        assert exc.value.status_code == 500

    def test_timeout_becomes_a_transport_error(self, config):
        def handler(request):
            raise httpx.ConnectTimeout("timed out", request=request)

        with build(config, handler) as client:
            with pytest.raises(EasyTimeTransportError):
                client.authenticate()

    def test_connection_refused_becomes_a_transport_error(self, config):
        # EasyTime Pro is a desktop service; "not running" is a normal state.
        def handler(request):
            raise httpx.ConnectError("connection refused", request=request)

        with build(config, handler) as client:
            with pytest.raises(EasyTimeTransportError):
                client.authenticate()

    def test_404_on_every_transactions_path_is_reported(self, discovering_config):
        def handler(request):
            if "token-auth" in request.url.path:
                return httpx.Response(200, json={"token": "tok"})
            return httpx.Response(404, text="nope")

        with build(discovering_config, handler) as client:
            with pytest.raises(EasyTimeResponseError):
                list(client.iter_transactions(DAY, DAY))


class TestSecrets:
    @pytest.mark.parametrize(
        "value",
        [
            {"token": "jwt-super-secret"},
            "Authorization: JWT abc",
            {"password": "hunter2"},
            {"access_token": "leak"},
        ],
    )
    def test_sanitize_redacts_secret_shaped_values(self, value):
        out = _sanitize(value)

        assert "secret" not in out
        assert "hunter2" not in out
        assert out.startswith("<redacted:")

    def test_http_error_body_is_sanitized(self, config):
        def handler(request):
            if "token-auth" in request.url.path:
                return httpx.Response(200, json={"token": "tok"})
            return httpx.Response(400, text='{"token": "leaked-token-value"}')

        with build(config, handler) as client:
            with pytest.raises(EasyTimeHTTPError) as exc:
                list(client.iter_transactions(DAY, DAY))

        assert "leaked-token-value" not in str(exc.value)

    def test_redacted_config_never_exposes_the_password(self, config):
        redacted = config.redacted()

        assert redacted["password"] == "***"
        assert config.password not in str(redacted)
