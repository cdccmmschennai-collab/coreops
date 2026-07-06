"""Unit tests for the central per-project permission helper (Phase 2 surface).

PM manages + reviews everything; the Head views + reviews their own project but
does not manage it or assign the Head; contributors are view-only; non-members
see nothing; the legacy team_lead reviewer path still grants review.
"""
from app.core import authz
from app.modules.projects.models import ProjectMemberRole
from app.modules.users.models import UserRole


def _emp(make_user, make_employee, email, code, role=UserRole.employee):
    u = make_user(email, role=role)
    e = make_employee(employee_code=code, user_id=u.id)
    return u, e


def _set_head(db, project, employee_id):
    project.head_employee_id = employee_id
    db.add(project)
    db.commit()


def test_pm_can_do_everything(db, make_user, make_project):
    pm = make_user("pm@x.com", role=UserRole.project_manager)
    project = make_project(code="A-1")
    assert authz.can_view_project(db, pm, project)
    assert authz.can_manage_project(db, pm, project)
    assert authz.can_assign_head(db, pm, project)
    assert authz.can_review_report(db, pm, {project.id})


def test_head_views_and_reviews_but_cannot_manage(db, make_user, make_employee, make_project):
    head_u, head_e = _emp(make_user, make_employee, "head@x.com", "H-1")
    project = make_project(code="A-2")
    _set_head(db, project, head_e.id)

    assert authz.is_project_head(db, head_u, project)
    assert authz.can_view_project(db, head_u, project)
    assert authz.can_review_report(db, head_u, {project.id})
    assert not authz.can_manage_project(db, head_u, project)
    assert not authz.can_assign_head(db, head_u, project)


def test_head_is_scoped_to_own_project(db, make_user, make_employee, make_project):
    head_u, head_e = _emp(make_user, make_employee, "head2@x.com", "H-2")
    mine = make_project(code="MINE")
    _set_head(db, mine, head_e.id)
    other = make_project(code="OTHER")

    assert not authz.is_project_head(db, head_u, other)
    assert not authz.can_view_project(db, head_u, other)
    assert not authz.can_review_report(db, head_u, {other.id})


def test_contributor_is_view_only(db, make_user, make_employee, make_project, make_project_member):
    u, e = _emp(make_user, make_employee, "c@x.com", "C-1")
    project = make_project(code="A-3")
    make_project_member(project_id=project.id, employee_id=e.id, role=ProjectMemberRole.contributor)

    assert authz.can_view_project(db, u, project)
    assert not authz.can_review_report(db, u, {project.id})
    assert not authz.can_manage_project(db, u, project)


def test_non_member_cannot_view_or_review(db, make_user, make_employee, make_project):
    u, _e = _emp(make_user, make_employee, "n@x.com", "N-1")
    project = make_project(code="A-4")
    assert not authz.can_view_project(db, u, project)
    assert not authz.can_review_report(db, u, {project.id})


def test_legacy_team_lead_can_still_review(db, make_user, make_employee, make_project, make_project_member):
    u, e = _emp(make_user, make_employee, "tl@x.com", "TL-1")
    project = make_project(code="A-5")
    make_project_member(project_id=project.id, employee_id=e.id, role=ProjectMemberRole.team_lead)

    assert authz.can_review_report(db, u, {project.id})
    assert authz.can_view_project(db, u, project)


def test_head_honored_by_review_among_multiple_projects(db, make_user, make_employee, make_project):
    """can_review_report is True when the caller heads ANY of the report's projects."""
    head_u, head_e = _emp(make_user, make_employee, "h3@x.com", "H-3")
    headed = make_project(code="HEADED")
    _set_head(db, headed, head_e.id)
    unrelated = make_project(code="UNREL")

    assert authz.can_review_report(db, head_u, {unrelated.id, headed.id})
    assert not authz.can_review_report(db, head_u, {unrelated.id})


def test_reviewable_project_ids_unions_head_and_team_lead(
    db, make_user, make_employee, make_project, make_project_member
):
    u, e = _emp(make_user, make_employee, "rv@x.com", "RV-1")
    headed = make_project(code="RV-H")
    _set_head(db, headed, e.id)
    led = make_project(code="RV-L")
    make_project_member(project_id=led.id, employee_id=e.id, role=ProjectMemberRole.team_lead)
    contrib = make_project(code="RV-C")
    make_project_member(project_id=contrib.id, employee_id=e.id, role=ProjectMemberRole.contributor)

    ids = authz.reviewable_project_ids(db, u)
    assert headed.id in ids and led.id in ids
    assert contrib.id not in ids  # a plain contributor cannot review
