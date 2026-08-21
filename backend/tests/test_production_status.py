"""Production Status - Phase 1 (data model, backend foundation, permissions).

Focused suite for the new module only. Covers, in order:

  1. migration / model creation      test_migration_created_table_and_indexes
  2. creating a production status    test_create_production_status
  3. retrieving latest status        test_latest_returns_newest_per_combination
  4. retrieving history              test_history_returns_every_update
  5. history preserved on update     test_history_preserved_after_status_change
  6. author is the real person       test_author_is_the_actual_user_name
  7. counts stored independently     test_counts_are_four_independent_values
  8. Project Manager authorization   test_project_manager_reads_any_project
  9. Project Head authorization      test_project_head_can_read_and_record
 10. Activity Lead authorization     test_activity_lead_can_record_own_activity_only
 11. unauthorized employee rejected  test_unrelated_employee_is_rejected
 12. invalid project/activity        test_invalid_project_and_activity_rejected
"""
from datetime import date

import pytest
from sqlalchemy import text

from app.modules.activity_master import service as am_svc
from app.modules.activity_master.schemas import ActivityCreate, SubActivityCreate
from app.modules.production_status import service as ps_svc
from app.modules.production_status.models import ProjectProductionStatus
from app.modules.production_status.schemas import ProductionStatusCreate
from app.modules.projects import service as proj_svc
from app.modules.projects.models import ProjectStatus
from app.modules.projects.schemas import ActivityMemberCreate
from app.modules.users.models import UserRole
from app.shared.errors import AppError


# --- helpers ---------------------------------------------------------------

def _activity(db, code):
    return am_svc.create_activity(db, ActivityCreate(code=code, name=code))


@pytest.fixture()
def scene(db, make_user, make_employee, make_project):
    """One project with a Head, one activity with a Lead, plus two outsiders.

      pm       project_manager, no assignment anywhere
      head_u   assigned Head of the project
      lead_u   Lead of activity FMTL on the project
      other_u  contributor on the project, leads nothing  -> not authorized
      alien_u  employee with no relation to the project   -> not authorized
    """
    class S:
        pass

    s = S()
    s.pm = make_user("pm@x.com", role=UserRole.project_manager)
    s.project = make_project(code="PS-1", name="Production Project",
                             status=ProjectStatus.active)

    s.head_u = make_user("head@x.com", role=UserRole.employee)
    s.head_e = make_employee(employee_code="H-1", first_name="Hema",
                             last_name="Rao", user_id=s.head_u.id)
    proj_svc.set_project_head(db, s.pm, s.project.id, s.head_e.id)

    s.activity = _activity(db, "FMTL")
    s.other_activity = _activity(db, "MTL")

    s.lead_u = make_user("lead@x.com", role=UserRole.employee)
    s.lead_e = make_employee(employee_code="L-1", first_name="Santhosh",
                             last_name="Kumar", user_id=s.lead_u.id)
    proj_svc.assign_activity_member(
        db, s.pm, s.project.id, s.activity.id,
        ActivityMemberCreate(employee_id=s.lead_e.id, role="lead"),
    )

    # A second activity IS on the project, but led by someone else - this is
    # what proves a Lead's authority is per-activity, not per-project.
    s.other_lead_u = make_user("otherlead@x.com", role=UserRole.employee)
    s.other_lead_e = make_employee(employee_code="L-2", user_id=s.other_lead_u.id)
    proj_svc.assign_activity_member(
        db, s.pm, s.project.id, s.other_activity.id,
        ActivityMemberCreate(employee_id=s.other_lead_e.id, role="lead"),
    )

    s.other_u = make_user("contrib@x.com", role=UserRole.employee)
    s.other_e = make_employee(employee_code="C-1", user_id=s.other_u.id)
    proj_svc.assign_activity_member(
        db, s.pm, s.project.id, s.activity.id,
        ActivityMemberCreate(employee_id=s.other_e.id, role="contributor"),
    )

    s.alien_u = make_user("alien@x.com", role=UserRole.employee)
    s.alien_e = make_employee(employee_code="A-1", user_id=s.alien_u.id)
    return s


def _payload(activity_id, **over):
    body = dict(
        revision="REV-0",
        activity_id=activity_id,
        status="in_progress",
        tag_count=180,
        doc_count=0,
        spares_count=0,
        crs_count=0,
    )
    body.update(over)
    return ProductionStatusCreate(**body)


# --- 1. migration / model creation -----------------------------------------

def test_migration_created_table_and_indexes(db):
    cols = {
        r[0]: (r[1], r[2])
        for r in db.execute(
            text(
                "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'project_production_statuses'"
            )
        ).all()
    }
    assert set(cols) == {
        "id", "project_id", "revision", "activity_id", "status",
        "tag_count", "doc_count", "spares_count", "crs_count",
        "completed_on", "remarks", "created_by", "created_at",
    }
    # Append-only: no updated_at, no soft-delete column (asserted by the set above).
    assert cols["tag_count"] == ("integer", "NO")
    assert cols["crs_count"] == ("integer", "NO")
    assert cols["completed_on"][0] == "date"
    assert cols["created_by"][1] == "NO"

    indexes = {
        r[0] for r in db.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'project_production_statuses'"
            )
        ).all()
    }
    assert "project_production_statuses_project_revision_activity_idx" in indexes
    assert "project_production_statuses_project_activity_created_idx" in indexes

    checks = {
        r[0] for r in db.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'project_production_statuses'::regclass AND contype = 'c'"
            )
        ).all()
    }
    assert "project_production_statuses_status_valid" in checks
    assert "project_production_statuses_counts_non_negative" in checks
    assert "project_production_statuses_revision_not_blank" in checks


# --- 2. creating a production status ---------------------------------------

def test_create_production_status(db, scene):
    out = ps_svc.create_production_status(
        db, scene.head_u, scene.project.id,
        _payload(scene.activity.id, remarks="First cut", completed_on=None),
    )
    assert out.project_id == scene.project.id
    assert out.project_code == "PS-1"
    assert out.project_name == "Production Project"
    assert out.revision == "REV-0"
    assert out.activity_id == scene.activity.id
    assert out.activity_name == "FMTL"
    assert out.status == "in_progress"
    assert out.tag_count == 180
    assert out.remarks == "First cut"
    assert db.query(ProjectProductionStatus).count() == 1


# --- 3. retrieving latest status -------------------------------------------

def test_latest_returns_newest_per_combination(db, scene):
    for tag, status in ((180, "in_progress"), (210, "in_progress"), (225, "closed")):
        ps_svc.create_production_status(
            db, scene.head_u, scene.project.id,
            _payload(scene.activity.id, tag_count=tag, status=status,
                     completed_on=date(2026, 12, 5) if status == "closed" else None),
        )
    # A different revision of the same activity is a separate current row.
    ps_svc.create_production_status(
        db, scene.head_u, scene.project.id,
        _payload(scene.activity.id, revision="REV-1", tag_count=12),
    )

    latest = ps_svc.list_latest(db, scene.head_u, scene.project.id)
    by_revision = {r.revision: r for r in latest}
    assert set(by_revision) == {"REV-0", "REV-1"}
    assert by_revision["REV-0"].status == "closed"
    assert by_revision["REV-0"].tag_count == 225
    assert by_revision["REV-0"].completed_on == date(2026, 12, 5)
    assert by_revision["REV-1"].tag_count == 12


# --- 4. retrieving history --------------------------------------------------

def test_history_returns_every_update(db, scene):
    for tag in (180, 210, 225):
        ps_svc.create_production_status(
            db, scene.head_u, scene.project.id,
            _payload(scene.activity.id, tag_count=tag),
        )
    ps_svc.create_production_status(
        db, scene.other_lead_u, scene.project.id,
        _payload(scene.other_activity.id, tag_count=7),
    )

    everything = ps_svc.list_history(db, scene.head_u, scene.project.id)
    assert len(everything) == 4

    scoped = ps_svc.list_history(
        db, scene.head_u, scene.project.id, activity_id=scene.activity.id
    )
    assert len(scoped) == 3
    assert {r.tag_count for r in scoped} == {180, 210, 225}

    by_revision = ps_svc.list_history(
        db, scene.head_u, scene.project.id,
        activity_id=scene.activity.id, revision="REV-0",
    )
    assert len(by_revision) == 3


# --- 5. history is preserved after a new update -----------------------------

def test_history_preserved_after_status_change(db, scene):
    first = ps_svc.create_production_status(
        db, scene.head_u, scene.project.id,
        _payload(scene.activity.id, tag_count=180, status="in_progress"),
    )
    ps_svc.create_production_status(
        db, scene.head_u, scene.project.id,
        _payload(scene.activity.id, tag_count=225, status="closed",
                 completed_on=date(2026, 12, 5)),
    )

    # The superseded INPROGRESS row is still there, byte for byte.
    original = db.get(ProjectProductionStatus, first.id)
    assert original is not None
    assert original.status == "in_progress"
    assert original.tag_count == 180

    history = ps_svc.list_history(
        db, scene.head_u, scene.project.id, activity_id=scene.activity.id
    )
    assert [(r.status, r.tag_count) for r in history] == [
        ("closed", 225), ("in_progress", 180),
    ]
    # ...while "current" is the new one.
    latest = ps_svc.list_latest(db, scene.head_u, scene.project.id)
    assert len(latest) == 1
    assert latest[0].status == "closed"


# --- 6. author is the user's actual name ------------------------------------

def test_author_is_the_actual_user_name(db, scene):
    out = ps_svc.create_production_status(
        db, scene.lead_u, scene.project.id, _payload(scene.activity.id)
    )
    assert out.created_by == scene.lead_u.id
    assert out.created_by_name == "Santhosh Kumar"
    # The role is never the author, and is not stored on the row at all.
    assert not hasattr(db.get(ProjectProductionStatus, out.id), "created_by_role")

    head_out = ps_svc.create_production_status(
        db, scene.head_u, scene.project.id, _payload(scene.activity.id, tag_count=5)
    )
    assert head_out.created_by_name == "Hema Rao"


# --- 7. TAG / DOC / SPARES / CRS stored independently -----------------------

def test_counts_are_four_independent_values(db, scene):
    out = ps_svc.create_production_status(
        db, scene.head_u, scene.project.id,
        _payload(scene.activity.id, tag_count=225, doc_count=14,
                 spares_count=3, crs_count=9),
    )
    assert (out.tag_count, out.doc_count, out.spares_count, out.crs_count) == (225, 14, 3, 9)

    row = db.get(ProjectProductionStatus, out.id)
    assert (row.tag_count, row.doc_count, row.spares_count, row.crs_count) == (225, 14, 3, 9)

    # Moving one unit leaves the other three untouched.
    later = ps_svc.create_production_status(
        db, scene.head_u, scene.project.id,
        _payload(scene.activity.id, tag_count=300, doc_count=14,
                 spares_count=3, crs_count=9),
    )
    assert later.tag_count == 300
    assert (later.doc_count, later.spares_count, later.crs_count) == (14, 3, 9)

    # A negative count never reaches the DB - rejected at the schema boundary.
    with pytest.raises(Exception):
        _payload(scene.activity.id, tag_count=-1)


# --- 8. Project Manager authorization ---------------------------------------

def test_project_manager_reads_any_project(db, scene):
    ps_svc.create_production_status(
        db, scene.head_u, scene.project.id, _payload(scene.activity.id)
    )
    # PM is assigned to nothing and still reads it.
    assert len(ps_svc.list_latest(db, scene.pm, scene.project.id)) == 1
    assert len(ps_svc.list_history(db, scene.pm, scene.project.id)) == 1


# --- 9. Project Head authorization ------------------------------------------

def test_project_head_can_read_and_record(db, scene, make_project):
    # The Head may record against ANY activity of their project, including one
    # they do not personally lead.
    out = ps_svc.create_production_status(
        db, scene.head_u, scene.project.id, _payload(scene.other_activity.id)
    )
    assert out.activity_id == scene.other_activity.id
    assert len(ps_svc.list_latest(db, scene.head_u, scene.project.id)) == 1

    # Heading project A grants nothing on project B.
    other_project = make_project(code="PS-2", status=ProjectStatus.active)
    with pytest.raises(AppError) as ei:
        ps_svc.list_latest(db, scene.head_u, other_project.id)
    assert ei.value.status_code == 403


# --- 10. Activity Lead authorization ----------------------------------------

def test_activity_lead_can_record_own_activity_only(db, scene):
    out = ps_svc.create_production_status(
        db, scene.lead_u, scene.project.id, _payload(scene.activity.id)
    )
    assert out.created_by == scene.lead_u.id

    # Leading FMTL does not grant MTL, even on the same project.
    with pytest.raises(AppError) as ei:
        ps_svc.create_production_status(
            db, scene.lead_u, scene.project.id, _payload(scene.other_activity.id)
        )
    assert ei.value.status_code == 403

    # Reading the project's production status is allowed for a lead.
    assert len(ps_svc.list_latest(db, scene.lead_u, scene.project.id)) == 1


# --- 11. unauthorized employee rejection ------------------------------------

def test_unrelated_employee_is_rejected(db, scene, client, login):
    ps_svc.create_production_status(
        db, scene.head_u, scene.project.id, _payload(scene.activity.id)
    )

    # A plain contributor on the project - can open the project, cannot open
    # Production Status, and cannot record.
    for actor in (scene.other_u, scene.alien_u):
        with pytest.raises(AppError) as ei:
            ps_svc.list_latest(db, actor, scene.project.id)
        assert ei.value.status_code == 403
        with pytest.raises(AppError) as ei:
            ps_svc.list_history(db, actor, scene.project.id)
        assert ei.value.status_code == 403
        with pytest.raises(AppError) as ei:
            ps_svc.create_production_status(
                db, actor, scene.project.id, _payload(scene.activity.id)
            )
        assert ei.value.status_code == 403

    # Same rule over HTTP, so the routes are actually wired to it.
    hdr = login("contrib@x.com")
    base = f"/api/v1/projects/{scene.project.id}/production-status"
    assert client.get(base, headers=hdr).status_code == 403
    assert client.get(f"{base}/history", headers=hdr).status_code == 403
    assert client.post(
        base,
        headers=hdr,
        json={"revision": "REV-0", "activity_id": str(scene.activity.id),
              "status": "in_progress", "tag_count": 1},
    ).status_code == 403


# --- 12. invalid project / activity rejection -------------------------------

def test_invalid_project_and_activity_rejected(db, scene, make_project):
    import uuid as _uuid

    # Unknown project.
    with pytest.raises(AppError) as ei:
        ps_svc.create_production_status(
            db, scene.pm, _uuid.uuid4(), _payload(scene.activity.id)
        )
    assert ei.value.status_code == 404

    # Unknown activity.
    with pytest.raises(AppError) as ei:
        ps_svc.create_production_status(
            db, scene.pm, scene.project.id, _payload(_uuid.uuid4())
        )
    assert ei.value.status_code == 404

    # A real activity that is not on this project.
    unrelated = _activity(db, "UNRELATED")
    with pytest.raises(AppError) as ei:
        ps_svc.create_production_status(
            db, scene.pm, scene.project.id, _payload(unrelated.id)
        )
    assert ei.value.status_code == 422

    # A sub-activity is not a valid production-status activity.
    sub = am_svc.create_sub_activity(
        db, scene.activity.id, SubActivityCreate(code="FMTL-1", name="FMTL step")
    )
    with pytest.raises(AppError) as ei:
        ps_svc.create_production_status(
            db, scene.pm, scene.project.id, _payload(sub.id)
        )
    assert ei.value.status_code == 422

    # Whitespace is not a revision label.
    with pytest.raises(AppError) as ei:
        ps_svc.create_production_status(
            db, scene.pm, scene.project.id,
            _payload(scene.activity.id, revision="   "),
        )
    assert ei.value.status_code == 422
