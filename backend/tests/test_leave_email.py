"""Tests for the leave emails: submission, approval and rejection.

Two layers, deliberately:

  * Recipient and failure behaviour are exercised against
    `leave.email.send_submission_email` / `send_approval_email` /
    `send_rejection_email` directly, with the LeaveRequest row built in place.
    That keeps them independent of the calendar and the work-report rules - which
    project a request routes to is `test_leave_routing.py`'s job, and re-deriving
    it here would only make these tests fail on Mondays.
  * The wiring - that submitting, approving and rejecting each really do email
    exactly once, and that the cancellation flows really do NOT - is exercised
    end to end through the API, because that is the property that would silently
    regress.

All three still render a `text/plain` body with no markup at all -
`_assert_no_markup` guards against the old designed-HTML format creeping back
into it - but now carry a minimal HTML alternative alongside it too, whose only
job is to make "View Leave Request" a real hyperlink with the CoreOps URL
hidden behind it rather than printed in the body. `_visible_text` strips that
HTML down to what a reader actually sees, so the raw-URL-must-not-be-visible
requirement can be asserted directly.

`enqueue_email` is replaced by a recorder in most tests, so nothing reaches
Celery, Redis or SMTP. The two tests that deliberately keep the real
`enqueue_email` are the broker-outage and email-disabled cases, which exist to
prove those degrade quietly.
"""
from datetime import date, timedelta

import pytest

from app.modules.leave import email as leave_email
from app.modules.leave.models import LeaveRequest, LeaveStatus, LeaveType
from app.modules.leave.recipients import resolve_leave_recipients
from app.modules.users.models import UserRole
from app.notifications.email_dispatch import EnqueueResult

_START = date(2026, 8, 28)
_END = date(2026, 8, 29)

# Every leave email is a single-part text/plain message. These are the tells of
# the designed-HTML format it must never go back to.
_MARKUP_TELLS = (
    "<table", "<div", "<button", "<a ", "<p ", "<td", "<tr", "<br", "<span",
    "style=", "background-color", "background:", "max-width", "cellpadding",
    "<!doctype", "<html", "&amp;", "&lt;", "&gt;", "&nbsp;",
)


def _assert_no_markup(body: str) -> None:
    lowered = body.lower()
    for tell in _MARKUP_TELLS:
        assert tell not in lowered, f"{tell!r} found in a plain-text email body"


def _visible_text(html_body: str) -> str:
    """Strip tags to approximate what a mail client actually renders to the eye
    - used to assert the raw URL is not part of the visible text."""
    import re

    return re.sub(r"<[^>]+>", "", html_body)


class _Recorder:
    """Stands in for `enqueue_email`, capturing what would have been queued."""

    def __init__(self, result=None):
        self.calls: list[dict] = []
        self._result = result or EnqueueResult(
            queued=True, task_id="task-1", recipients=()
        )

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self._result

    @property
    def recipients(self) -> list:
        return [c["to"] for c in self.calls]


@pytest.fixture()
def recorder(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(leave_email, "enqueue_email", rec)
    return rec


class _StubSettings:
    """Enabled, configured email settings, without touching the environment."""

    EMAIL_ENABLED = True

    @property
    def is_configured(self):
        return True


def _leave(db, employee_id, *, routed_project_id=None, reason="Personal reasons"):
    req = LeaveRequest(
        employee_id=employee_id,
        leave_type=LeaveType.casual,
        start_date=_START,
        end_date=_END,
        reason=reason,
        status=LeaveStatus.pending,
        routed_project_id=routed_project_id,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


# ---------- recipient resolution -------------------------------------------

def test_routed_head_with_a_work_email_is_the_recipient(
    db, make_user, make_employee, make_project, recorder,
):
    hu = make_user("head-e1@x.com")
    head = make_employee(
        employee_code="HE1", first_name="Head", last_name="One",
        user_id=hu.id, work_email="head.one@cdccmms.com",
    )
    project = make_project(code="EM-1", head_employee_id=head.id)
    emp = make_employee(employee_code="EE1", first_name="Karthikeyan", last_name="K")
    req = _leave(db, emp.id, routed_project_id=project.id)

    leave_email.send_submission_email(db, emp, req)

    assert recorder.recipients == ["head.one@cdccmms.com"]
    assert recorder.calls[0]["subject"] == (
        "Leave Request - Karthikeyan K - Action Required"
    )


def test_every_leave_email_carries_a_minimal_html_alternative(
    db, make_employee, recorder, monkeypatch,
):
    """Every leave send hands `enqueue_email` both a markup-free `text_body` and
    a minimal `html_body` whose only clickable element is "View Leave Request",
    with the CoreOps URL hidden behind it rather than printed in the visible
    text. None of the three pass `text_only=True` any more - that flag would
    suppress the HTML alternative outright, and a hidden URL is impossible
    without it."""
    import html as html_module

    from app.core.config import settings

    monkeypatch.setattr(settings, "APP_BASE_URL", "https://coreops.cdccmms.com")

    reviewer = make_employee(employee_code="RV15", work_email="rv15@cdccmms.com")
    mgr = make_employee(employee_code="MG15", work_email="mgr.15@cdccmms.com")
    emp = make_employee(
        employee_code="EE15", manager_id=mgr.id, work_email="emp.15@cdccmms.com"
    )
    req = _leave(db, emp.id)
    link = leave_email.build_link(leave_email.leave_request_path(req, is_head=False))
    escaped_href = html_module.escape(link, quote=True)

    leave_email.send_submission_email(db, emp, req)
    leave_email.send_approval_email(db, req, reviewer)
    leave_email.send_rejection_email(db, req, reviewer)

    assert len(recorder.calls) == 3
    for call in recorder.calls:
        assert not call.get("text_only")
        _assert_no_markup(call["text_body"])
        assert "View Leave Request" in call["text_body"]

        html_body = call["html_body"]
        assert "<b>View Leave Request</b></a>" in html_body
        assert f'href="{escaped_href}"' in html_body
        assert link not in _visible_text(html_body)
        # No card, no button, no table-based layout - a letter, not a design.
        for tell in ("<table", "<button", "background", "<img", "class="):
            assert tell not in html_body.lower()


def test_head_without_a_work_email_falls_back_to_the_manager(
    db, make_user, make_employee, make_project, recorder,
):
    """The Head has a LOGIN but no work email. The bell still reaches them (the
    in-app channel only needs `user_id`); only the email falls through."""
    hu = make_user("head-e2@x.com")
    head = make_employee(employee_code="HE2", user_id=hu.id, work_email=None)
    project = make_project(code="EM-2", head_employee_id=head.id)
    mgr = make_employee(employee_code="MG2", work_email="mgr.two@cdccmms.com")
    emp = make_employee(employee_code="EE2", manager_id=mgr.id)
    req = _leave(db, emp.id, routed_project_id=project.id)

    leave_email.send_submission_email(db, emp, req)

    assert recorder.recipients == ["mgr.two@cdccmms.com"]
    # The chain itself still puts the Head first - only the email's own
    # reachability test skipped them.
    chain = resolve_leave_recipients(db, emp, req)
    assert [c.is_head for c in chain] == [True, False]


def test_head_login_email_is_never_used_as_the_work_email(
    db, make_user, make_employee, make_project, recorder,
):
    """`User.email` is a login identity, not a work address. A Head who can sign
    in but has no `work_email` must NOT be emailed at their login address."""
    hu = make_user("head-login@x.com")
    head = make_employee(employee_code="HE3", user_id=hu.id, work_email=None)
    project = make_project(code="EM-3", head_employee_id=head.id)
    mgr = make_employee(employee_code="MG3", work_email="mgr.three@cdccmms.com")
    emp = make_employee(employee_code="EE3", manager_id=mgr.id)
    req = _leave(db, emp.id, routed_project_id=project.id)

    leave_email.send_submission_email(db, emp, req)

    assert recorder.recipients == ["mgr.three@cdccmms.com"]
    assert "head-login@x.com" not in recorder.recipients


def test_no_routed_project_falls_back_to_the_manager(
    db, make_employee, recorder,
):
    mgr = make_employee(employee_code="MG4", work_email="mgr.four@cdccmms.com")
    emp = make_employee(employee_code="EE4", manager_id=mgr.id)
    req = _leave(db, emp.id, routed_project_id=None)

    leave_email.send_submission_email(db, emp, req)

    assert recorder.recipients == ["mgr.four@cdccmms.com"]


def test_project_without_a_head_falls_back_to_the_manager(
    db, make_employee, make_project, recorder,
):
    project = make_project(code="EM-5")  # no head_employee_id
    mgr = make_employee(employee_code="MG5", work_email="mgr.five@cdccmms.com")
    emp = make_employee(employee_code="EE5", manager_id=mgr.id)
    req = _leave(db, emp.id, routed_project_id=project.id)

    leave_email.send_submission_email(db, emp, req)

    assert recorder.recipients == ["mgr.five@cdccmms.com"]


def test_the_requester_is_never_emailed_about_their_own_request(
    db, make_employee, make_project, recorder,
):
    """The employee IS the routed project's Head. Emailing them their own
    submission is noise, and they may not review it either."""
    mgr = make_employee(employee_code="MG6", work_email="mgr.six@cdccmms.com")
    emp = make_employee(
        employee_code="EE6", manager_id=mgr.id, work_email="self.six@cdccmms.com"
    )
    project = make_project(code="EM-6", head_employee_id=emp.id)
    req = _leave(db, emp.id, routed_project_id=project.id)

    leave_email.send_submission_email(db, emp, req)

    assert recorder.recipients == ["mgr.six@cdccmms.com"]
    assert "self.six@cdccmms.com" not in recorder.recipients


def test_head_with_no_user_account_is_still_emailed(
    db, make_employee, make_project, recorder,
):
    """Email needs an address, not a login. A Head with no linked User row is
    unreachable by the bell but perfectly reachable by email."""
    head = make_employee(
        employee_code="HE7", user_id=None, work_email="head.seven@cdccmms.com"
    )
    project = make_project(code="EM-7", head_employee_id=head.id)
    mgr = make_employee(employee_code="MG7", work_email="mgr.seven@cdccmms.com")
    emp = make_employee(employee_code="EE7", manager_id=mgr.id)
    req = _leave(db, emp.id, routed_project_id=project.id)

    leave_email.send_submission_email(db, emp, req)

    assert recorder.recipients == ["head.seven@cdccmms.com"]


def test_a_blank_work_email_counts_as_no_work_email(
    db, make_employee, make_project, recorder,
):
    head = make_employee(employee_code="HE8", work_email="   ")
    project = make_project(code="EM-8", head_employee_id=head.id)
    mgr = make_employee(employee_code="MG8", work_email="mgr.eight@cdccmms.com")
    emp = make_employee(employee_code="EE8", manager_id=mgr.id)
    req = _leave(db, emp.id, routed_project_id=project.id)

    leave_email.send_submission_email(db, emp, req)

    assert recorder.recipients == ["mgr.eight@cdccmms.com"]


def test_nobody_with_a_work_email_sends_nothing(
    db, make_employee, make_project, recorder,
):
    head = make_employee(employee_code="HE9", work_email=None)
    project = make_project(code="EM-9", head_employee_id=head.id)
    mgr = make_employee(employee_code="MG9", work_email=None)
    emp = make_employee(employee_code="EE9", manager_id=mgr.id)
    req = _leave(db, emp.id, routed_project_id=project.id)

    leave_email.send_submission_email(db, emp, req)

    assert recorder.calls == []


def test_no_recipients_at_all_sends_nothing(db, make_employee, recorder):
    """No routed project and no manager - a legitimate state, not an error."""
    emp = make_employee(employee_code="EE10", manager_id=None)
    req = _leave(db, emp.id, routed_project_id=None)

    leave_email.send_submission_email(db, emp, req)

    assert recorder.calls == []


# ---------- failure behaviour ----------------------------------------------

def test_a_dead_broker_does_not_raise(db, make_employee, monkeypatch):
    """Real `enqueue_email`, dead Celery. The leave request is already committed
    by this point, so an outage must degrade to a log line."""
    import app.notifications.email_dispatch as dispatch
    import app.tasks.email_tasks as email_tasks

    class _DeadTask:
        def delay(self, payload):
            raise OSError("connection refused")

    monkeypatch.setattr(email_tasks, "send_email", _DeadTask())
    monkeypatch.setattr(dispatch, "get_email_settings", lambda: _StubSettings())

    mgr = make_employee(employee_code="MG11", work_email="mgr.eleven@cdccmms.com")
    emp = make_employee(employee_code="EE11", manager_id=mgr.id)
    req = _leave(db, emp.id)

    leave_email.send_submission_email(db, emp, req)  # must not raise


def test_disabled_email_does_not_raise_and_never_reaches_the_broker(
    db, make_employee, monkeypatch,
):
    import app.notifications.email_dispatch as dispatch
    import app.tasks.email_tasks as email_tasks

    class _Disabled:
        EMAIL_ENABLED = False

        @property
        def is_configured(self):
            return True

    class _Boom:
        def delay(self, payload):
            raise AssertionError("a disabled mailer must not reach the broker")

    monkeypatch.setattr(email_tasks, "send_email", _Boom())
    monkeypatch.setattr(dispatch, "get_email_settings", lambda: _Disabled())

    mgr = make_employee(employee_code="MG12", work_email="mgr.twelve@cdccmms.com")
    emp = make_employee(employee_code="EE12", manager_id=mgr.id)
    req = _leave(db, emp.id)

    leave_email.send_submission_email(db, emp, req)  # must not raise


def test_a_renderer_failure_does_not_escape(db, make_employee, monkeypatch):
    """Last-resort isolation: even a bug in this module must not reach a caller
    whose leave request has already been committed."""
    mgr = make_employee(employee_code="MG13", work_email="mgr.13@cdccmms.com")
    emp = make_employee(employee_code="EE13", manager_id=mgr.id)
    req = _leave(db, emp.id)

    def _boom(**kwargs):
        raise RuntimeError("template exploded")

    monkeypatch.setattr(leave_email, "render_submission_email", _boom)

    leave_email.send_submission_email(db, emp, req)  # must not raise


# ---------- rendering -------------------------------------------------------

def _render(**overrides):
    kwargs = {
        "recipient_name": "Giridharan",
        "employee_name": "Karthikeyan K",
        "leave_type": LeaveType.casual,
        "start_date": _START,
        "end_date": _END,
        "reason": "Personal reasons",
        "request_id": "11111111-2222-3333-4444-555555555555",
        "link": "https://coreops.cdccmms.com/attendance?tab=leave&id=abc",
    }
    kwargs.update(overrides)
    return leave_email.render_submission_email(**kwargs)


def test_subject_names_the_employee_and_the_action():
    assert _render().subject == "Leave Request - Karthikeyan K - Action Required"


def test_body_carries_the_business_facts():
    body = _render().text_body
    assert "Karthikeyan K" in body
    assert "Casual Leave" in body
    assert "28 Aug 2026 - 29 Aug 2026" in body
    assert "Personal reasons" in body
    assert "requires your review" in body


def test_the_submission_body_is_plain_text_with_no_markup():
    """The whole point of this format: it must look like an email a colleague
    typed, not a designed notification."""
    _assert_no_markup(_render().text_body)


def test_the_submission_body_matches_the_agreed_letter_shape():
    assert _render().text_body == "\n".join([
        "Dear Giridharan,",
        "",
        "A new leave request has been submitted by Karthikeyan K and requires "
        "your review.",
        "",
        "Leave Type: Casual Leave",
        "Leave Period: 28 Aug 2026 - 29 Aug 2026 (2 days)",
        "Reason: Personal reasons",
        "",
        "Please review the request and approve or reject it through the CoreOps "
        "system.",
        "",
        "View Leave Request:",
        "https://coreops.cdccmms.com/attendance?tab=leave&id=abc",
        "",
        "Regards,",
        "CoreOps",
        "",
        "Request ID: 11111111-2222-3333-4444-555555555555",
        "Automated notification - please do not reply.",
    ])


def test_a_single_day_leave_is_not_rendered_as_a_range():
    rendered = _render(end_date=_START)
    assert "28 Aug 2026 - " not in rendered.text_body
    assert "28 Aug 2026" in rendered.text_body


def test_the_greeting_names_the_actual_recipient():
    """Never "Dear Project Head" - the reader may be the manager fallback, and a
    role is not a name either way."""
    body = _render(recipient_name="Giridharan").text_body
    assert body.startswith("Dear Giridharan,\n")
    assert "Dear Project Head" not in body


def test_the_period_states_the_day_count():
    assert "28 Aug 2026 - 29 Aug 2026 (2 days)" in _render().text_body
    assert "28 Aug 2026 (1 day)" in _render(end_date=_START).text_body


def test_leave_day_count_is_the_inclusive_calendar_span():
    assert leave_email.leave_day_count(_START, _START) == 1
    assert leave_email.leave_day_count(_START, _END) == 2
    assert leave_email.leave_day_count(_START, date(2026, 9, 3)) == 7


def test_a_missing_reason_omits_the_row_entirely():
    for reason in (None, "", "   "):
        assert "Reason:" not in _render(reason=reason).text_body


def test_the_link_is_rendered_as_a_plain_url_on_its_own_line():
    """No anchor, no button - the bare absolute URL under a label, so Outlook
    autolinks it and a wrapping client cannot break it in half."""
    body = _render().text_body
    assert "View Leave Request:\nhttps://coreops.cdccmms.com/attendance?tab=leave&id=abc" in body
    assert "href=" not in body
    assert "&amp;" not in body


def test_no_link_means_no_call_to_action():
    assert "View Leave Request" not in _render(link=None).text_body
    assert "View Leave Request" not in _render(link=None).html_body


def test_the_html_link_hides_the_url_behind_view_leave_request():
    """The one presentation difference from the text body: the HTML alternative
    must render "View Leave Request" as the clickable text, with the CoreOps URL
    only in the href, never in what the reader sees."""
    import html as html_module

    rendered = _render()
    link = "https://coreops.cdccmms.com/attendance?tab=leave&id=abc"
    escaped_href = html_module.escape(link, quote=True)

    assert f'href="{escaped_href}"' in rendered.html_body
    assert "<b>View Leave Request</b></a>" in rendered.html_body
    assert link not in _visible_text(rendered.html_body)
    assert "coreops.cdccmms.com" not in _visible_text(rendered.html_body)


def test_the_html_body_has_no_marketing_layout():
    """No card, no button, no table, no image, no background - a letter, not a
    designed notification."""
    html_body = _render().html_body.lower()
    for tell in (
        "<table", "<button", "background", "<img", "class=", "<center",
        "border-radius", "cellpadding", "max-width",
    ):
        assert tell not in html_body


def test_the_html_body_carries_the_same_facts_as_the_text_body():
    rendered = _render()
    text = _visible_text(rendered.html_body)
    assert "Karthikeyan K" in text
    assert "Casual Leave" in text
    assert "Personal reasons" in text
    assert "Dear Giridharan," in text


def test_the_request_id_stays_in_the_footer_not_the_message():
    rendered = _render()
    body, _, footer = rendered.text_body.partition("Regards,")
    assert "11111111-2222-3333-4444-555555555555" not in body
    assert "11111111-2222-3333-4444-555555555555" in footer


def test_no_implementation_details_leak_into_the_email():
    lowered = _render().text_body.lower()
    for leak in ("routed_project", "celery", "redis", "brevo", "smtp", "postgres"):
        assert leak not in lowered


def test_untrusted_text_is_passed_through_verbatim_not_escaped():
    """A plain-text body has nothing to escape INTO. HTML entities here would be
    a bug the reader sees, not a defence."""
    body = _render(employee_name="A & B", reason="1 < 2 & 3 > 2").text_body
    assert "A & B" in body
    assert "1 < 2 & 3 > 2" in body
    assert "&amp;" not in body
    assert "&lt;" not in body


def test_leave_type_labels_cover_every_stored_value():
    for leave_type in LeaveType:
        label = leave_email.leave_type_label(leave_type)
        assert label and "_" not in label


def test_build_link_needs_a_configured_base_url(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "APP_BASE_URL", "")
    assert leave_email.build_link("/attendance?tab=leave") is None

    monkeypatch.setattr(settings, "APP_BASE_URL", "https://coreops.cdccmms.com/")
    assert leave_email.build_link("/attendance?tab=leave") == (
        "https://coreops.cdccmms.com/attendance?tab=leave"
    )


# ---------- decision rendering ----------------------------------------------

def _decision(**overrides):
    kwargs = {
        "approved": True,
        "employee_name": "Santhosh Kumar",
        "reviewer_name": "Giridharan",
        "leave_type": LeaveType.casual,
        "start_date": _START,
        "end_date": _END,
        "reason": "Personal reasons",
        "reviewer_comment": None,
        "request_id": "11111111-2222-3333-4444-555555555555",
        "link": "https://coreops.cdccmms.com/attendance?tab=leave&id=abc",
    }
    kwargs.update(overrides)
    return leave_email.render_decision_email(**kwargs)


def test_the_decision_subjects_state_the_outcome():
    assert _decision(approved=True).subject == "Leave Request - Approved"
    assert _decision(approved=False).subject == "Leave Request - Rejected"


def test_the_approval_body_carries_the_business_facts():
    body = _decision(approved=True).text_body
    assert "Dear Santhosh Kumar," in body
    assert "approved by" in body
    assert "Giridharan" in body
    assert "Casual Leave" in body
    assert "28 Aug 2026 - 29 Aug 2026 (2 days)" in body
    assert "View Leave Request" in body
    assert "CoreOps" in body


def test_the_approval_body_matches_the_agreed_letter_shape():
    assert _decision(approved=True, end_date=_START).text_body == "\n".join([
        "Dear Santhosh Kumar,",
        "",
        "Your leave request has been approved by Giridharan.",
        "",
        "Leave Type: Casual Leave",
        "Leave Period: 28 Aug 2026 (1 day)",
        "",
        "Your leave request has been successfully approved in the CoreOps system.",
        "",
        "View Leave Request:",
        "https://coreops.cdccmms.com/attendance?tab=leave&id=abc",
        "",
        "Regards,",
        "CoreOps",
        "",
        "Request ID: 11111111-2222-3333-4444-555555555555",
        "Automated notification - please do not reply.",
    ])


def test_the_rejection_body_carries_the_business_facts():
    body = _decision(
        approved=False, reviewer_comment="Leave cannot be approved for these dates."
    ).text_body
    assert "Dear Santhosh Kumar," in body
    assert "rejected by" in body
    assert "Giridharan" in body
    assert "Casual Leave" in body
    assert "28 Aug 2026 - 29 Aug 2026 (2 days)" in body
    # The employee's own reason, and the reviewer's answer to it.
    assert "Personal reasons" in body
    assert "Leave cannot be approved for these dates." in body
    assert "Reviewer Comment" in body


def test_both_decision_bodies_are_plain_text_with_no_markup():
    for approved in (True, False):
        _assert_no_markup(
            _decision(approved=approved, reviewer_comment="Peak week").text_body
        )


def test_a_rejection_without_a_comment_renders_no_empty_section():
    for comment in (None, "", "   "):
        assert "Reviewer Comment" not in _decision(
            approved=False, reviewer_comment=comment
        ).text_body


def test_a_rejection_without_a_reason_omits_the_row_and_invents_nothing():
    rendered = _decision(approved=False, reason=None, reviewer_comment=None)
    assert "Reason:" not in rendered.text_body


def test_an_approval_does_not_echo_the_reason_or_a_comment_back():
    """The answer is yes; repeating the reader's own words adds nothing."""
    body = _decision(
        approved=True, reason="Personal reasons", reviewer_comment="Fine by me"
    ).text_body
    assert "Reason:" not in body
    assert "Reviewer Comment" not in body


def test_a_single_day_decision_states_one_day():
    rendered = _decision(end_date=_START)
    assert "28 Aug 2026 (1 day)" in rendered.text_body
    assert "28 Aug 2026 - " not in rendered.text_body


def test_an_unknown_reviewer_drops_the_clause_rather_than_naming_nobody():
    rendered = _decision(reviewer_name=None)
    assert "Your leave request has been approved." in rendered.text_body
    assert " by " not in rendered.text_body.split("\n")[2]


def test_a_decision_without_a_link_has_no_call_to_action():
    assert "View Leave Request" not in _decision(link=None).text_body
    assert "View Leave Request" not in _decision(link=None).html_body


def test_a_decision_html_link_hides_the_url_behind_view_leave_request():
    import html as html_module

    rendered = _decision(approved=True)
    link = "https://coreops.cdccmms.com/attendance?tab=leave&id=abc"
    escaped_href = html_module.escape(link, quote=True)

    assert f'href="{escaped_href}"' in rendered.html_body
    assert "<b>View Leave Request</b></a>" in rendered.html_body
    assert link not in _visible_text(rendered.html_body)


def test_a_decision_html_body_has_no_marketing_layout():
    for approved in (True, False):
        html_body = _decision(
            approved=approved, reviewer_comment="Peak week"
        ).html_body.lower()
        for tell in (
            "<table", "<button", "background", "<img", "class=", "<center",
            "border-radius", "cellpadding", "max-width",
        ):
            assert tell not in html_body


def test_a_decision_html_body_carries_the_same_facts_as_the_text_body():
    approved = _decision(approved=True)
    approved_text = _visible_text(approved.html_body)
    assert "Dear Santhosh Kumar," in approved_text
    assert "Giridharan" in approved_text
    assert "Casual Leave" in approved_text

    rejected = _decision(
        approved=False, reviewer_comment="Leave cannot be approved for these dates."
    )
    rejected_text = _visible_text(rejected.html_body)
    assert "Personal reasons" in rejected_text
    assert "Leave cannot be approved for these dates." in rejected_text
    assert "Reviewer Comment" in rejected_text


def test_the_decision_request_id_stays_in_the_footer():
    rendered = _decision()
    body, _, footer = rendered.text_body.partition("Regards,")
    assert "11111111-2222-3333-4444-555555555555" not in body
    assert "11111111-2222-3333-4444-555555555555" in footer


def test_no_implementation_details_leak_into_a_decision_email():
    lowered = _decision(approved=False, reviewer_comment="No").text_body.lower()
    for leak in ("routed_project", "celery", "redis", "brevo", "smtp", "postgres"):
        assert leak not in lowered


def test_a_decision_passes_untrusted_text_through_verbatim():
    body = _decision(
        approved=False,
        employee_name="A & B",
        reviewer_name="R & Co",
        reason="1 < 2",
        reviewer_comment="Not this week & not next",
    ).text_body
    assert "A & B" in body
    assert "R & Co" in body
    assert "1 < 2" in body
    assert "Not this week & not next" in body
    assert "&amp;" not in body


# ---------- decision recipient + failure behaviour ---------------------------

def _decided(db, employee_id, *, reviewer_id=None, comment=None):
    """A leave request in its post-decision, committed shape."""
    req = _leave(db, employee_id)
    req.manager_id = reviewer_id
    req.manager_comment = comment
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def test_approval_emails_the_requesting_employees_work_email(
    db, make_employee, recorder,
):
    reviewer = make_employee(employee_code="RV30", first_name="Giri", last_name="D")
    emp = make_employee(
        employee_code="EE30", first_name="Santhosh", last_name="Kumar",
        work_email="santhosh.kumar@cdccmms.com",
    )
    req = _decided(db, emp.id, reviewer_id=reviewer.id)

    leave_email.send_approval_email(db, req, reviewer)

    assert recorder.recipients == ["santhosh.kumar@cdccmms.com"]
    assert recorder.calls[0]["subject"] == "Leave Request - Approved"
    body = recorder.calls[0]["text_body"]
    assert "Dear Santhosh Kumar," in body
    assert "Giri D" in body
    assert "Casual Leave" in body
    assert "28 Aug 2026 - 29 Aug 2026 (2 days)" in body


def test_rejection_emails_the_requesting_employee_with_the_comment(
    db, make_employee, recorder,
):
    reviewer = make_employee(employee_code="RV31", first_name="Giri", last_name="D")
    emp = make_employee(
        employee_code="EE31", first_name="Santhosh", last_name="Kumar",
        work_email="santhosh.31@cdccmms.com",
    )
    req = _decided(db, emp.id, reviewer_id=reviewer.id, comment="Peak delivery week.")

    leave_email.send_rejection_email(db, req, reviewer)

    assert recorder.recipients == ["santhosh.31@cdccmms.com"]
    assert recorder.calls[0]["subject"] == "Leave Request - Rejected"
    body = recorder.calls[0]["text_body"]
    assert "Dear Santhosh Kumar," in body
    assert "Peak delivery week." in body
    assert "Personal reasons" in body


def test_a_decision_never_emails_the_reviewer_or_the_manager(
    db, make_employee, recorder,
):
    """No chain is walked: the outcome of a request is nobody's business but the
    requester's, so there is no Head/manager rung to fall through to."""
    reviewer = make_employee(employee_code="RV32", work_email="reviewer.32@cdccmms.com")
    mgr = make_employee(employee_code="MG32", work_email="mgr.32@cdccmms.com")
    emp = make_employee(
        employee_code="EE32", manager_id=mgr.id, work_email="emp.32@cdccmms.com"
    )
    req = _decided(db, emp.id, reviewer_id=reviewer.id)

    leave_email.send_approval_email(db, req, reviewer)

    assert recorder.recipients == ["emp.32@cdccmms.com"]


def test_a_decision_for_an_employee_without_a_work_email_sends_nothing(
    db, make_employee, recorder,
):
    for code, work_email in (("EE33", None), ("EE34", "   ")):
        emp = make_employee(employee_code=code, work_email=work_email)
        req = _decided(db, emp.id)

        leave_email.send_approval_email(db, req, None)
        leave_email.send_rejection_email(db, req, None)

    assert recorder.calls == []


def test_a_decision_never_falls_back_to_the_login_email(
    db, make_user, make_employee, recorder,
):
    """`User.email` is a login identity. An employee who can sign in but has no
    `work_email` must NOT be emailed at their login address."""
    u = make_user("emp-login-35@x.com")
    emp = make_employee(employee_code="EE35", user_id=u.id, work_email=None)
    req = _decided(db, emp.id)

    leave_email.send_approval_email(db, req, None)
    leave_email.send_rejection_email(db, req, None)

    assert recorder.calls == []


def test_a_dead_broker_does_not_break_a_decision_email(db, make_employee, monkeypatch):
    import app.notifications.email_dispatch as dispatch
    import app.tasks.email_tasks as email_tasks

    class _DeadTask:
        def delay(self, payload):
            raise OSError("connection refused")

    monkeypatch.setattr(email_tasks, "send_email", _DeadTask())
    monkeypatch.setattr(dispatch, "get_email_settings", lambda: _StubSettings())

    emp = make_employee(employee_code="EE36", work_email="emp.36@cdccmms.com")
    req = _decided(db, emp.id)

    leave_email.send_approval_email(db, req, None)  # must not raise
    leave_email.send_rejection_email(db, req, None)  # must not raise


def test_disabled_email_never_reaches_the_broker_for_a_decision(
    db, make_employee, monkeypatch,
):
    import app.notifications.email_dispatch as dispatch
    import app.tasks.email_tasks as email_tasks

    class _Disabled:
        EMAIL_ENABLED = False

        @property
        def is_configured(self):
            return True

    class _Boom:
        def delay(self, payload):
            raise AssertionError("a disabled mailer must not reach the broker")

    monkeypatch.setattr(email_tasks, "send_email", _Boom())
    monkeypatch.setattr(dispatch, "get_email_settings", lambda: _Disabled())

    emp = make_employee(employee_code="EE37", work_email="emp.37@cdccmms.com")
    req = _decided(db, emp.id)

    leave_email.send_approval_email(db, req, None)  # must not raise
    leave_email.send_rejection_email(db, req, None)  # must not raise


def test_a_decision_renderer_failure_does_not_escape(db, make_employee, monkeypatch):
    emp = make_employee(employee_code="EE38", work_email="emp.38@cdccmms.com")
    req = _decided(db, emp.id)

    def _boom(**kwargs):
        raise RuntimeError("template exploded")

    monkeypatch.setattr(leave_email, "render_decision_email", _boom)

    leave_email.send_approval_email(db, req, None)  # must not raise
    leave_email.send_rejection_email(db, req, None)  # must not raise


def test_an_empty_app_base_url_drops_the_decision_link_but_still_renders(
    db, make_employee, recorder, monkeypatch,
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "APP_BASE_URL", "")
    emp = make_employee(employee_code="EE39", work_email="emp.39@cdccmms.com")
    req = _decided(db, emp.id)

    leave_email.send_approval_email(db, req, None)

    assert recorder.recipients == ["emp.39@cdccmms.com"]
    body = recorder.calls[0]["text_body"]
    assert "View Leave Request" not in body
    assert "/attendance" not in body


def test_a_configured_app_base_url_produces_an_absolute_decision_link(
    db, make_employee, recorder, monkeypatch,
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "APP_BASE_URL", "https://coreops.cdccmms.com")
    emp = make_employee(employee_code="EE40", work_email="emp.40@cdccmms.com")
    req = _decided(db, emp.id)

    leave_email.send_approval_email(db, req, None)

    expected = f"https://coreops.cdccmms.com/attendance?tab=leave&id={req.id}"
    assert expected in recorder.calls[0]["text_body"]
    # The same path the in-app `leave_approved` notification deep-links to.
    assert f"/attendance?tab=leave&id={req.id}" == leave_email.leave_request_path(
        req, is_head=False
    )


# ---------- end-to-end wiring ----------------------------------------------

def _recent_working_day() -> date:
    day = date.today()
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _next_working_day(after: date) -> date:
    day = after + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def _payload(start: date, end: date, leave_type: str = "casual") -> dict:
    return {
        "leave_type": leave_type,
        "start_date": str(start),
        "end_date": str(end),
        "reason": "Family trip",
    }


def test_submitting_emails_the_head_and_still_rings_the_bell(
    client, db, make_user, make_employee, make_project, make_project_member,
    login, recorder,
):
    """The whole path: report -> routed project -> Head -> email, with the
    existing in-app notification untouched alongside it."""
    from app.modules.notifications.models import Notification
    from app.modules.work_reports import service as wr_svc
    from app.modules.work_reports.schemas import WorkReportCreate, WorkReportTaskIn

    hu = make_user("head-e2e@x.com")
    head = make_employee(
        employee_code="HE20", user_id=hu.id, work_email="head.e2e@cdccmms.com"
    )
    project = make_project(code="EM-20", head_employee_id=head.id)

    eu = make_user("emp-e2e@x.com")
    emp = make_employee(
        employee_code="EE20", first_name="Karthikeyan", last_name="K", user_id=eu.id
    )
    make_project_member(project_id=project.id, employee_id=emp.id)

    prev_day = _recent_working_day()
    leave_date = _next_working_day(prev_day)
    wr_svc.create_work_report(
        db, eu, WorkReportCreate(
            report_date=prev_day,
            tasks=[WorkReportTaskIn(
                project_id=project.id, description="work", minutes_spent=120
            )],
        ),
    )

    res = client.post(
        "/api/v1/leave-requests",
        headers=login("emp-e2e@x.com"),
        json=_payload(leave_date, leave_date),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["routed_project_id"] == str(project.id)

    # The email went to the Head's work email...
    assert recorder.recipients == ["head.e2e@cdccmms.com"]
    assert "Karthikeyan K" in recorder.calls[0]["subject"]

    # ...and the in-app notification is exactly as it was before this phase.
    note = db.query(Notification).filter(Notification.user_id == hu.id).one()
    assert note.type == "leave_submitted"
    assert note.target_url == f"/attendance?tab=leave&queue=pending&id={body['id']}"


def _decision_fixture(db, make_user, make_employee):
    """A manager who may review, an employee who may be emailed, and a balance
    large enough for the approvals these tests perform."""
    from decimal import Decimal

    from app.modules.leave_balances import ledger
    from app.modules.leave_balances.models import EmployeeLeaveAdjustment

    mu = make_user("mgr-e2e@x.com", role=UserRole.project_manager)
    mgr = make_employee(employee_code="MG21", user_id=mu.id,
                        first_name="Giri", last_name="Dharan",
                        work_email="mgr.e2e@cdccmms.com")
    eu = make_user("emp-dec@x.com")
    emp = make_employee(employee_code="EE21", user_id=eu.id, manager_id=mgr.id,
                        first_name="Santhosh", last_name="Kumar",
                        work_email="santhosh.e2e@cdccmms.com")

    db.add(EmployeeLeaveAdjustment(
        employee_id=emp.id,
        effective_month=ledger.month_start(date.today()),
        days=Decimal("30.00"),
        reason="Opening balance",
    ))
    db.commit()
    return mgr, emp, eu


def test_each_leave_event_emails_exactly_once_and_only_the_right_ones(
    client, db, make_user, make_employee, login, recorder,
):
    """Submission, approval and rejection each email once; the cancellation
    flows email nothing. This is the regression that would otherwise slip in the
    day somebody moves a send into `_push` - which all six leave notification
    events share - instead of the two decision functions."""
    _decision_fixture(db, make_user, make_employee)

    h_emp = login("emp-dec@x.com")
    h_mgr = login("mgr-e2e@x.com")
    start = date.today() + timedelta(days=7)

    # Submit: one email, to the approver.
    first = client.post(
        "/api/v1/leave-requests", headers=h_emp, json=_payload(start, start)
    )
    assert first.status_code == 201, first.text
    assert len(recorder.calls) == 1
    assert recorder.calls[0]["to"] == "mgr.e2e@cdccmms.com"
    assert recorder.calls[0]["subject"] == (
        "Leave Request - Santhosh Kumar - Action Required"
    )

    # Approve: a second email, this one to the employee.
    approved = client.post(
        f"/api/v1/leave-requests/{first.json()['id']}/approve", headers=h_mgr, json={}
    )
    assert approved.status_code == 200, approved.text
    assert len(recorder.calls) == 2
    assert recorder.calls[1]["to"] == "santhosh.e2e@cdccmms.com"
    assert recorder.calls[1]["subject"] == "Leave Request - Approved"
    assert "Giri Dharan" in recorder.calls[1]["text_body"]

    # A second request, rejected: one submission email, one rejection email.
    second_start = start + timedelta(days=14)
    second = client.post(
        "/api/v1/leave-requests", headers=h_emp, json=_payload(second_start, second_start)
    )
    assert second.status_code == 201, second.text
    assert len(recorder.calls) == 3

    rejected = client.post(
        f"/api/v1/leave-requests/{second.json()['id']}/reject",
        headers=h_mgr,
        json={"comment": "Peak delivery week."},
    )
    assert rejected.status_code == 200, rejected.text
    assert len(recorder.calls) == 4
    assert recorder.calls[3]["to"] == "santhosh.e2e@cdccmms.com"
    assert recorder.calls[3]["subject"] == "Leave Request - Rejected"
    assert "Peak delivery week." in recorder.calls[3]["text_body"]

    # And a cancellation by the employee: the submission emails, the cancel does
    # not.
    third_start = start + timedelta(days=28)
    third = client.post(
        "/api/v1/leave-requests", headers=h_emp, json=_payload(third_start, third_start)
    )
    assert third.status_code == 201, third.text
    assert len(recorder.calls) == 5

    cancelled = client.post(
        f"/api/v1/leave-requests/{third.json()['id']}/cancel", headers=h_emp
    )
    assert cancelled.status_code == 200, cancelled.text
    assert len(recorder.calls) == 5


def test_the_cancellation_withdrawal_flow_sends_no_decision_email(
    client, db, make_user, make_employee, login, recorder,
):
    """Requesting withdrawal of an approved leave, and the manager's decision on
    that request, are cancellation events - not leave decisions. None of the
    three may reach the decision-email path."""
    _decision_fixture(db, make_user, make_employee)

    h_emp = login("emp-dec@x.com")
    h_mgr = login("mgr-e2e@x.com")
    start = date.today() + timedelta(days=7)

    created = client.post(
        "/api/v1/leave-requests", headers=h_emp, json=_payload(start, start)
    )
    assert created.status_code == 201, created.text
    req_id = created.json()["id"]

    approved = client.post(
        f"/api/v1/leave-requests/{req_id}/approve", headers=h_mgr, json={}
    )
    assert approved.status_code == 200, approved.text
    after_approval = len(recorder.calls)  # 1 submission + 1 approval
    assert after_approval == 2

    asked = client.post(
        f"/api/v1/leave-requests/{req_id}/request-cancellation", headers=h_emp
    )
    assert asked.status_code == 200, asked.text
    assert len(recorder.calls) == after_approval

    decided = client.post(
        f"/api/v1/leave-requests/{req_id}/approve-cancellation", headers=h_mgr
    )
    assert decided.status_code == 200, decided.text
    assert len(recorder.calls) == after_approval


def test_the_decision_bell_still_rings_alongside_the_email(
    client, db, make_user, make_employee, login, recorder,
):
    """The email is an ADDITION. The existing `leave_approved` /
    `leave_rejected` notifications, and their target_url, are untouched."""
    from app.modules.notifications.models import Notification

    _mgr, _emp, eu = _decision_fixture(db, make_user, make_employee)

    h_emp = login("emp-dec@x.com")
    h_mgr = login("mgr-e2e@x.com")
    start = date.today() + timedelta(days=7)

    first = client.post(
        "/api/v1/leave-requests", headers=h_emp, json=_payload(start, start)
    ).json()
    client.post(
        f"/api/v1/leave-requests/{first['id']}/approve", headers=h_mgr, json={}
    )

    second_start = start + timedelta(days=14)
    second = client.post(
        "/api/v1/leave-requests", headers=h_emp, json=_payload(second_start, second_start)
    ).json()
    client.post(
        f"/api/v1/leave-requests/{second['id']}/reject", headers=h_mgr, json={}
    )

    notes = {
        n.type: n
        for n in db.query(Notification).filter(Notification.user_id == eu.id).all()
    }
    assert "leave_approved" in notes
    assert notes["leave_approved"].target_url == (
        f"/attendance?tab=leave&id={first['id']}"
    )
    assert "leave_rejected" in notes
    assert notes["leave_rejected"].target_url == (
        f"/attendance?tab=leave&id={second['id']}"
    )


def test_a_decision_for_an_employee_without_a_work_email_still_succeeds(
    client, db, make_user, make_employee, login, recorder,
):
    """The API must not turn "nowhere to mail this" into an error."""
    from decimal import Decimal

    from app.modules.leave_balances import ledger
    from app.modules.leave_balances.models import EmployeeLeaveAdjustment
    from app.modules.notifications.models import Notification

    mu = make_user("mgr-nomail@x.com", role=UserRole.project_manager)
    mgr = make_employee(employee_code="MG23", user_id=mu.id,
                        work_email="mgr.23@cdccmms.com")
    eu = make_user("emp-nomail@x.com")
    emp = make_employee(employee_code="EE23", user_id=eu.id, manager_id=mgr.id,
                        work_email=None)
    db.add(EmployeeLeaveAdjustment(
        employee_id=emp.id,
        effective_month=ledger.month_start(date.today()),
        days=Decimal("30.00"),
        reason="Opening balance",
    ))
    db.commit()

    h_emp = login("emp-nomail@x.com")
    h_mgr = login("mgr-nomail@x.com")
    start = date.today() + timedelta(days=7)

    first = client.post(
        "/api/v1/leave-requests", headers=h_emp, json=_payload(start, start)
    )
    assert first.status_code == 201, first.text
    assert len(recorder.calls) == 1  # the submission email to the manager

    approved = client.post(
        f"/api/v1/leave-requests/{first.json()['id']}/approve", headers=h_mgr, json={}
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert len(recorder.calls) == 1  # nothing queued for the employee

    second_start = start + timedelta(days=14)
    second = client.post(
        "/api/v1/leave-requests", headers=h_emp, json=_payload(second_start, second_start)
    )
    assert second.status_code == 201, second.text
    rejected = client.post(
        f"/api/v1/leave-requests/{second.json()['id']}/reject", headers=h_mgr, json={}
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
    assert len(recorder.calls) == 2  # only the two submission emails

    # The bell rang for both decisions regardless.
    types = {
        n.type for n in db.query(Notification).filter(Notification.user_id == eu.id).all()
    }
    assert {"leave_approved", "leave_rejected"} <= types


def test_a_broker_outage_does_not_fail_a_decision(
    client, db, make_user, make_employee, login, monkeypatch,
):
    """Redis down: approve and reject still return 200 and stay committed."""
    import app.notifications.email_dispatch as dispatch
    import app.tasks.email_tasks as email_tasks

    class _DeadTask:
        def delay(self, payload):
            raise OSError("connection refused")

    monkeypatch.setattr(email_tasks, "send_email", _DeadTask())
    monkeypatch.setattr(dispatch, "get_email_settings", lambda: _StubSettings())

    _decision_fixture(db, make_user, make_employee)

    h_emp = login("emp-dec@x.com")
    h_mgr = login("mgr-e2e@x.com")
    start = date.today() + timedelta(days=7)

    first = client.post(
        "/api/v1/leave-requests", headers=h_emp, json=_payload(start, start)
    )
    assert first.status_code == 201, first.text
    approved = client.post(
        f"/api/v1/leave-requests/{first.json()['id']}/approve", headers=h_mgr, json={}
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    second_start = start + timedelta(days=14)
    second = client.post(
        "/api/v1/leave-requests", headers=h_emp, json=_payload(second_start, second_start)
    )
    assert second.status_code == 201, second.text
    rejected = client.post(
        f"/api/v1/leave-requests/{second.json()['id']}/reject", headers=h_mgr, json={}
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"


def test_a_broker_outage_does_not_fail_the_submission(
    client, make_user, make_employee, login, monkeypatch,
):
    """The API keeps serving with Redis down: the request is created and returned
    201, and only the email is lost."""
    import app.notifications.email_dispatch as dispatch
    import app.tasks.email_tasks as email_tasks

    class _DeadTask:
        def delay(self, payload):
            raise OSError("connection refused")

    monkeypatch.setattr(email_tasks, "send_email", _DeadTask())
    monkeypatch.setattr(dispatch, "get_email_settings", lambda: _StubSettings())

    mgr = make_employee(employee_code="MG22", work_email="mgr.22@cdccmms.com")
    eu = make_user("emp-broker@x.com")
    make_employee(employee_code="EE22", user_id=eu.id, manager_id=mgr.id)

    start = date.today() + timedelta(days=7)
    res = client.post(
        "/api/v1/leave-requests",
        headers=login("emp-broker@x.com"),
        json=_payload(start, start),
    )

    assert res.status_code == 201, res.text
    assert res.json()["status"] == "pending"
