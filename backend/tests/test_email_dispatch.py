"""Tests for the reusable asynchronous email capability.

Independent by construction: nothing here touches the database, a broker, a
worker or a real SMTP server. The Celery task is exercised by calling its
underlying function directly, and the enqueue path by substituting the task
object — so the whole suite runs with Redis stopped.

Covered:
  * recipient normalisation (blanks, case-insensitive de-duplication, order)
  * payload build/validate, including every EmailPayloadError condition
  * attachment base64 round-trip and the queued-size cap
  * deliver_payload against a stub EmailService, incl. the version guard
  * enqueue_email: the happy path, each declined reason, and a dead broker
  * the task's retry configuration and its registration on the Celery app
"""
import base64

import pytest

from app.notifications.email_dispatch import (
    MAX_ASYNC_ATTACHMENT_BYTES,
    MAX_RECIPIENTS,
    MAX_SUBJECT_LENGTH,
    PAYLOAD_VERSION,
    REASON_BROKER_UNAVAILABLE,
    REASON_EMAIL_DISABLED,
    REASON_NOT_CONFIGURED,
    REASON_NO_RECIPIENTS,
    EmailPayloadError,
    build_payload,
    deliver_payload,
    enqueue_email,
    normalise_recipients,
    payload_to_attachments,
    send_email_now,
)
from app.notifications.email_service import Attachment, EmailSendError

_HTML = "<p>Hello</p>"


# --- doubles ----------------------------------------------------------------


class _StubEmailService:
    """Records what it was asked to send; optionally fails."""

    def __init__(self, *, result=True, error=None):
        self._result = result
        self._error = error
        self.sends = []

    def send(self, *, to, subject, html_body, text_body=None, attachments=None):
        self.sends.append(
            {
                "to": to,
                "subject": subject,
                "html_body": html_body,
                "text_body": text_body,
                "attachments": attachments,
            }
        )
        if self._error is not None:
            raise self._error
        return self._result


class _StubSettings:
    """Stands in for EmailSettings without touching the environment."""

    def __init__(self, *, enabled=True, configured=True):
        self.EMAIL_ENABLED = enabled
        self._configured = configured

    @property
    def is_configured(self):
        return self._configured


class _StubTask:
    """Stands in for the Celery task object `enqueue_email` imports."""

    def __init__(self, *, task_id="task-1", error=None):
        self._task_id = task_id
        self._error = error
        self.payloads = []

    def delay(self, payload):
        if self._error is not None:
            raise self._error
        self.payloads.append(payload)
        return type("R", (), {"id": self._task_id})()


@pytest.fixture
def stub_task(monkeypatch):
    """Install a fake task so enqueue_email never reaches Celery or Redis."""
    import app.tasks.email_tasks as email_tasks

    task = _StubTask()
    monkeypatch.setattr(email_tasks, "send_email", task)
    return task


def _enabled():
    return _StubSettings(enabled=True, configured=True)


# --- recipient normalisation ------------------------------------------------


def test_normalise_accepts_a_bare_string():
    assert normalise_recipients("a@x.com") == ["a@x.com"]


def test_normalise_trims_and_drops_blanks():
    assert normalise_recipients(["  a@x.com  ", "", "   ", None]) == ["a@x.com"]


def test_normalise_deduplicates_case_insensitively_keeping_first_spelling():
    """work_email / users.email are CITEXT: two spellings are one mailbox, and
    resolving the same person twice must not produce two emails."""
    got = normalise_recipients(["Head@X.com", "head@x.com", "HEAD@X.COM", "b@x.com"])
    assert got == ["Head@X.com", "b@x.com"]


def test_normalise_preserves_order():
    assert normalise_recipients(["c@x.com", "a@x.com", "b@x.com"]) == [
        "c@x.com",
        "a@x.com",
        "b@x.com",
    ]


def test_normalise_of_nothing_is_empty():
    assert normalise_recipients(None) == []
    assert normalise_recipients([]) == []
    assert normalise_recipients("") == []


# --- payload building -------------------------------------------------------


def test_build_payload_shape():
    payload = build_payload(
        to="a@x.com", subject="  Subject  ", html_body=_HTML, text_body="Hello"
    )
    assert payload == {
        "version": PAYLOAD_VERSION,
        "to": ["a@x.com"],
        "subject": "Subject",          # trimmed
        "html_body": _HTML,
        "text_body": "Hello",
        "attachments": [],
    }


def test_build_payload_is_json_safe():
    """Celery's serializer is JSON; a payload it cannot encode is undeliverable."""
    import json

    payload = build_payload(
        to=["a@x.com"],
        subject="S",
        html_body=_HTML,
        attachments=[Attachment(filename="r.csv", content=b"a,b\n1,2\n")],
    )
    assert json.loads(json.dumps(payload)) == payload


def test_build_payload_rejects_empty_subject():
    with pytest.raises(EmailPayloadError, match="subject must not be empty"):
        build_payload(to="a@x.com", subject="   ", html_body=_HTML)


def test_build_payload_rejects_oversized_subject():
    with pytest.raises(EmailPayloadError, match="max"):
        build_payload(
            to="a@x.com", subject="x" * (MAX_SUBJECT_LENGTH + 1), html_body=_HTML
        )


def test_build_payload_rejects_empty_html_body():
    with pytest.raises(EmailPayloadError, match="html_body must not be empty"):
        build_payload(to="a@x.com", subject="S", html_body="   ")


def test_build_payload_rejects_too_many_recipients():
    many = [f"user{i}@x.com" for i in range(MAX_RECIPIENTS + 1)]
    with pytest.raises(EmailPayloadError, match="Too many recipients"):
        build_payload(to=many, subject="S", html_body=_HTML)


def test_build_payload_allows_exactly_the_recipient_limit():
    many = [f"user{i}@x.com" for i in range(MAX_RECIPIENTS)]
    payload = build_payload(to=many, subject="S", html_body=_HTML)
    assert len(payload["to"]) == MAX_RECIPIENTS


def test_build_payload_normalises_recipients():
    payload = build_payload(
        to=["A@x.com", "a@x.com", " "], subject="S", html_body=_HTML
    )
    assert payload["to"] == ["A@x.com"]


def test_build_payload_allows_no_recipients():
    """Validation of *the message* is separate from having somewhere to send it;
    enqueue_email is what declines an empty recipient list."""
    assert build_payload(to=[], subject="S", html_body=_HTML)["to"] == []


# --- attachments ------------------------------------------------------------


def test_attachment_round_trip_preserves_bytes_and_mime_type():
    content = b"\x00\x01\x02 binary, not text \xff"
    payload = build_payload(
        to="a@x.com",
        subject="S",
        html_body=_HTML,
        attachments=[
            Attachment(
                filename="r.xlsx",
                content=content,
                maintype="application",
                subtype="vnd.ms-excel",
            )
        ],
    )
    assert base64.b64decode(payload["attachments"][0]["content_b64"]) == content

    [restored] = payload_to_attachments(payload)
    assert restored.filename == "r.xlsx"
    assert restored.content == content
    assert restored.maintype == "application"
    assert restored.subtype == "vnd.ms-excel"


def test_attachment_defaults_match_the_attachment_dataclass():
    payload = build_payload(
        to="a@x.com",
        subject="S",
        html_body=_HTML,
        attachments=[Attachment(filename="r.csv", content=b"x")],
    )
    [restored] = payload_to_attachments(payload)
    assert (restored.maintype, restored.subtype) == ("text", "csv")


def test_attachments_over_the_queue_cap_are_refused():
    oversized = b"x" * (MAX_ASYNC_ATTACHMENT_BYTES + 1)
    with pytest.raises(EmailPayloadError, match="too large to queue"):
        build_payload(
            to="a@x.com",
            subject="S",
            html_body=_HTML,
            attachments=[Attachment(filename="big.bin", content=oversized)],
        )


def test_the_cap_is_on_the_total_not_each_attachment():
    half = b"x" * (MAX_ASYNC_ATTACHMENT_BYTES // 2 + 1)
    with pytest.raises(EmailPayloadError, match="too large to queue"):
        build_payload(
            to="a@x.com",
            subject="S",
            html_body=_HTML,
            attachments=[
                Attachment(filename="a.bin", content=half),
                Attachment(filename="b.bin", content=half),
            ],
        )


def test_corrupt_attachment_base64_is_a_payload_error():
    payload = build_payload(to="a@x.com", subject="S", html_body=_HTML)
    payload["attachments"] = [
        {"filename": "r.csv", "content_b64": "not base64!!", "maintype": "text",
         "subtype": "csv"}
    ]
    with pytest.raises(EmailPayloadError, match="not valid"):
        payload_to_attachments(payload)


# --- deliver_payload (worker side) ------------------------------------------


def test_deliver_payload_passes_everything_through_to_the_email_service():
    service = _StubEmailService()
    payload = build_payload(
        to=["a@x.com", "b@x.com"],
        subject="S",
        html_body=_HTML,
        text_body="Hello",
        attachments=[Attachment(filename="r.csv", content=b"x")],
    )

    assert deliver_payload(payload, email_service=service) is True

    [sent] = service.sends
    assert sent["to"] == ["a@x.com", "b@x.com"]
    assert sent["subject"] == "S"
    assert sent["html_body"] == _HTML
    assert sent["text_body"] == "Hello"
    assert [a.filename for a in sent["attachments"]] == ["r.csv"]


def test_deliver_payload_passes_none_when_there_are_no_attachments():
    """EmailService takes `attachments: list | None`; an empty list would make it
    iterate nothing, but None is the shape every existing caller passes."""
    service = _StubEmailService()
    deliver_payload(build_payload(to="a@x.com", subject="S", html_body=_HTML),
                    email_service=service)
    assert service.sends[0]["attachments"] is None


def test_deliver_payload_returns_false_when_the_service_skips():
    """EMAIL_ENABLED=false makes EmailService.send return False - a skip, not a
    failure, and it must surface as one."""
    service = _StubEmailService(result=False)
    payload = build_payload(to="a@x.com", subject="S", html_body=_HTML)
    assert deliver_payload(payload, email_service=service) is False


def test_deliver_payload_propagates_send_errors_for_the_task_to_retry():
    service = _StubEmailService(error=EmailSendError("relay down"))
    payload = build_payload(to="a@x.com", subject="S", html_body=_HTML)
    with pytest.raises(EmailSendError):
        deliver_payload(payload, email_service=service)


def test_deliver_payload_refuses_an_unknown_payload_version():
    """A worker running older code during a rolling deploy must refuse a shape it
    does not understand rather than mis-send it."""
    payload = build_payload(to="a@x.com", subject="S", html_body=_HTML)
    payload["version"] = PAYLOAD_VERSION + 1
    with pytest.raises(EmailPayloadError, match="Unsupported email payload version"):
        deliver_payload(payload, email_service=_StubEmailService())


# --- enqueue_email ----------------------------------------------------------


def test_enqueue_queues_the_payload_and_reports_the_task_id(stub_task):
    result = enqueue_email(
        to="a@x.com",
        subject="S",
        html_body=_HTML,
        text_body="Hello",
        settings=_enabled(),
    )

    assert result.queued is True
    assert result.task_id == "task-1"
    assert result.reason is None
    assert result.recipients == ("a@x.com",)

    [payload] = stub_task.payloads
    assert payload["to"] == ["a@x.com"]
    assert payload["subject"] == "S"
    assert payload["version"] == PAYLOAD_VERSION


def test_enqueue_deduplicates_before_queueing(stub_task):
    result = enqueue_email(
        to=["Head@X.com", "head@x.com"],
        subject="S",
        html_body=_HTML,
        settings=_enabled(),
    )
    assert result.recipients == ("Head@X.com",)
    assert stub_task.payloads[0]["to"] == ["Head@X.com"]


def test_enqueue_declines_with_no_recipients(stub_task):
    result = enqueue_email(to=["", None], subject="S", html_body=_HTML,
                           settings=_enabled())

    assert result.queued is False
    assert result.reason == REASON_NO_RECIPIENTS
    assert result.skipped is True
    assert stub_task.payloads == []


def test_enqueue_declines_when_email_is_disabled(stub_task):
    """EMAIL_ENABLED=false costs nothing at all - no broker round trip, no worker
    wake-up that ends in a skip."""
    result = enqueue_email(
        to="a@x.com",
        subject="S",
        html_body=_HTML,
        settings=_StubSettings(enabled=False),
    )

    assert result.queued is False
    assert result.reason == REASON_EMAIL_DISABLED
    assert result.skipped is True
    assert result.recipients == ("a@x.com",)
    assert stub_task.payloads == []


def test_enqueue_declines_when_smtp_is_not_configured(stub_task):
    result = enqueue_email(
        to="a@x.com",
        subject="S",
        html_body=_HTML,
        settings=_StubSettings(enabled=True, configured=False),
    )

    assert result.queued is False
    assert result.reason == REASON_NOT_CONFIGURED
    # Not a "skip": a configured-on but unconfigured relay is an operator error.
    assert result.skipped is False
    assert stub_task.payloads == []


def test_a_dead_broker_never_raises_at_the_call_site(monkeypatch):
    """The API keeps serving with the worker/broker stopped, so an enqueue during
    a Redis outage must degrade to a reported failure, not a 500."""
    import app.tasks.email_tasks as email_tasks

    monkeypatch.setattr(
        email_tasks, "send_email", _StubTask(error=OSError("connection refused"))
    )

    result = enqueue_email(
        to="a@x.com", subject="S", html_body=_HTML, settings=_enabled()
    )

    assert result.queued is False
    assert result.reason == REASON_BROKER_UNAVAILABLE
    # Distinguished from a deliberate skip so callers can alert on it.
    assert result.skipped is False


def test_a_malformed_message_raises_at_the_call_site(stub_task):
    """A caller bug fails identically on every retry, so it surfaces where it was
    made rather than in a worker log the caller never reads."""
    with pytest.raises(EmailPayloadError):
        enqueue_email(to="a@x.com", subject="", html_body=_HTML, settings=_enabled())
    assert stub_task.payloads == []


def test_enqueue_never_sends_synchronously(stub_task, monkeypatch):
    """The whole point of this module: no SMTP work on the caller's thread, even
    as a fallback."""
    import app.notifications.email_dispatch as dispatch

    def _boom(*args, **kwargs):
        raise AssertionError("enqueue_email must not construct an EmailService")

    monkeypatch.setattr(dispatch, "EmailService", _boom)
    assert enqueue_email(
        to="a@x.com", subject="S", html_body=_HTML, settings=_enabled()
    ).queued is True


# --- send_email_now ---------------------------------------------------------


def test_send_email_now_delivers_through_the_same_validation():
    service = _StubEmailService()
    assert send_email_now(
        to=["A@x.com", "a@x.com"],
        subject="  S  ",
        html_body=_HTML,
        email_service=service,
    ) is True
    assert service.sends[0]["to"] == ["A@x.com"]     # de-duplicated
    assert service.sends[0]["subject"] == "S"        # trimmed


def test_send_email_now_with_no_recipients_sends_nothing():
    service = _StubEmailService()
    assert send_email_now(to=[], subject="S", html_body=_HTML,
                          email_service=service) is False
    assert service.sends == []


def test_send_email_now_rejects_a_malformed_message():
    with pytest.raises(EmailPayloadError):
        send_email_now(to="a@x.com", subject="S", html_body="",
                       email_service=_StubEmailService())


# --- the Celery task itself -------------------------------------------------


def test_task_is_registered_under_its_documented_name():
    from app.core.celery_app import EMAIL_SEND_TASK, celery_app
    import app.tasks.email_tasks  # noqa: F401 - registers the task

    assert EMAIL_SEND_TASK == "coreops.notifications.send_email"
    assert EMAIL_SEND_TASK in celery_app.tasks


def test_task_module_is_in_the_worker_include_list():
    """A task in a module the worker never imports is never registered, and every
    call to it dies as 'Received unregistered task'."""
    from app.core.celery_app import celery_app

    assert "app.tasks.email_tasks" in celery_app.conf.include
    # The pre-existing module must still be there.
    assert "app.tasks.periodic_tasks" in celery_app.conf.include


def test_task_retries_only_transport_failures():
    from app.tasks.email_tasks import EMAIL_MAX_RETRIES, send_email

    assert send_email.autoretry_for == (EmailSendError,)
    assert send_email.max_retries == EMAIL_MAX_RETRIES
    assert send_email.retry_backoff is True
    assert send_email.retry_jitter is True
    # A malformed payload must NOT be retried - it fails identically every time.
    assert EmailPayloadError not in send_email.autoretry_for


def test_task_body_reports_a_successful_send(monkeypatch):
    import app.tasks.email_tasks as email_tasks

    monkeypatch.setattr(email_tasks, "deliver_payload", lambda payload: True)
    payload = build_payload(to=["a@x.com", "b@x.com"], subject="S", html_body=_HTML)

    assert email_tasks.send_email.run(payload) == {
        "sent": True,
        "recipients": 2,
        "attempts": 1,
    }


def test_task_body_reports_a_skip_without_failing(monkeypatch):
    """EMAIL_ENABLED=false is a success with sent=False; retrying it would be an
    infinite no-op."""
    import app.tasks.email_tasks as email_tasks

    monkeypatch.setattr(email_tasks, "deliver_payload", lambda payload: False)
    payload = build_payload(to="a@x.com", subject="S", html_body=_HTML)

    assert email_tasks.send_email.run(payload)["sent"] is False


def test_task_body_reraises_send_errors_so_celery_can_retry(monkeypatch):
    import app.tasks.email_tasks as email_tasks

    def _fail(payload):
        raise EmailSendError("relay down")

    monkeypatch.setattr(email_tasks, "deliver_payload", _fail)
    payload = build_payload(to="a@x.com", subject="S", html_body=_HTML)

    with pytest.raises(EmailSendError):
        email_tasks.send_email.run(payload)
