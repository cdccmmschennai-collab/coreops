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

Phase 3 (workflow hardening) adds, without changing the Phase 1 model:

 13. revision isolation              test_revision_history_never_shows_another_revision
 14. activity isolation              test_updating_one_activity_leaves_the_others_alone
 15. multiple authors in one trail   test_each_update_keeps_its_own_author
 16. no de-duplication               test_identical_updates_both_recorded
 17. date is a plain calendar date   test_completed_on_is_a_calendar_date
 18. multiline remarks preserved     test_multiline_remarks_are_preserved
 19. nothing can edit or delete      test_module_exposes_no_update_or_delete
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
        # Migration 0071 - the record's selected Maintenance Plant. Nullable,
        # so every row written before 0071 is still valid.
        "maintenance_plant_id",
        # Migration 0072 - the typed activity name, for an activity that is not
        # in Activity Master.
        "activity_label",
    }
    assert cols["maintenance_plant_id"] == ("uuid", "YES")
    # 0072: BOTH activity columns are nullable, because exactly one of them is
    # set on any given row - which is what the CHECK below enforces.
    assert cols["activity_id"] == ("uuid", "YES")
    assert cols["activity_label"][1] == "YES"
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
    # 0072: an activity named exactly once - an id OR a typed label.
    assert "project_production_statuses_activity_named_once" in checks
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
            db, scene.head_u, _uuid.uuid4(), _payload(scene.activity.id)
        )
    assert ei.value.status_code == 404

    # Unknown activity.
    with pytest.raises(AppError) as ei:
        ps_svc.create_production_status(
            db, scene.head_u, scene.project.id, _payload(_uuid.uuid4())
        )
    assert ei.value.status_code == 404

    # An Activity Master activity this project is NOT staffed for is ACCEPTED
    # now: the Head owns the project's whole output and reports against every
    # activity, not only the ones somebody happens to be assigned to. Requiring
    # staffing left a project with none unable to record anything at all.
    unrelated = _activity(db, "UNRELATED")
    out = ps_svc.create_production_status(
        db, scene.head_u, scene.project.id, _payload(unrelated.id)
    )
    assert out.activity_name == "UNRELATED"

    # A sub-activity is still not a valid production-status activity.
    sub = am_svc.create_sub_activity(
        db, scene.activity.id, SubActivityCreate(code="FMTL-1", name="FMTL step")
    )
    with pytest.raises(AppError) as ei:
        ps_svc.create_production_status(
            db, scene.head_u, scene.project.id, _payload(sub.id)
        )
    assert ei.value.status_code == 422

    # Whitespace is not a revision label.
    with pytest.raises(AppError) as ei:
        ps_svc.create_production_status(
            db, scene.head_u, scene.project.id,
            _payload(scene.activity.id, revision="   "),
        )
    assert ei.value.status_code == 422


# ===========================================================================
# Phase 3 - workflow hardening. Nothing below changes the Phase 1 model; each
# test pins a guarantee the PM cumulative export will depend on.
# ===========================================================================

# --- 13. revision isolation --------------------------------------------------

def test_revision_history_never_shows_another_revision(db, scene):
    """REV-0 and REV-1 of the SAME activity are two independent trails."""
    for tag in (100, 180, 225):
        ps_svc.create_production_status(
            db, scene.head_u, scene.project.id,
            _payload(scene.activity.id, revision="REV-0", tag_count=tag,
                     status="closed" if tag == 225 else "in_progress",
                     completed_on=date(2025, 12, 5) if tag == 225 else None),
        )
    for tag in (50, 300):
        ps_svc.create_production_status(
            db, scene.head_u, scene.project.id,
            _payload(scene.activity.id, revision="REV-1", tag_count=tag),
        )

    rev0 = ps_svc.list_history(
        db, scene.head_u, scene.project.id,
        activity_id=scene.activity.id, revision="REV-0",
    )
    rev1 = ps_svc.list_history(
        db, scene.head_u, scene.project.id,
        activity_id=scene.activity.id, revision="REV-1",
    )
    assert {r.revision for r in rev0} == {"REV-0"}
    assert {r.revision for r in rev1} == {"REV-1"}
    assert [r.tag_count for r in rev0] == [225, 180, 100]   # newest first
    assert [r.tag_count for r in rev1] == [300, 50]
    # Neither trail leaked into the other.
    assert not ({r.id for r in rev0} & {r.id for r in rev1})

    # Both revisions stay side by side in the current view - never merged.
    latest = {r.revision: r for r in ps_svc.list_latest(db, scene.head_u, scene.project.id)}
    assert set(latest) == {"REV-0", "REV-1"}
    assert (latest["REV-0"].status, latest["REV-0"].tag_count) == ("closed", 225)
    assert (latest["REV-1"].status, latest["REV-1"].tag_count) == ("in_progress", 300)

    # Closing REV-0 did not touch REV-1's own record.
    assert latest["REV-1"].completed_on is None


# --- 14. activity isolation --------------------------------------------------

def test_updating_one_activity_leaves_the_others_alone(db, scene):
    """Recording against FMTL must not alter MTL's current status."""
    fmtl = ps_svc.create_production_status(
        db, scene.head_u, scene.project.id,
        _payload(scene.activity.id, tag_count=120, doc_count=7),
    )
    mtl = ps_svc.create_production_status(
        db, scene.head_u, scene.project.id,
        _payload(scene.other_activity.id, tag_count=500, doc_count=1),
    )

    # A second FMTL update - MTL's row must be untouched, in the DB and in the
    # derived "latest" view.
    ps_svc.create_production_status(
        db, scene.head_u, scene.project.id,
        _payload(scene.activity.id, tag_count=140, doc_count=7),
    )

    mtl_row = db.get(ProjectProductionStatus, mtl.id)
    assert (mtl_row.tag_count, mtl_row.doc_count, mtl_row.status) == (500, 1, "in_progress")

    latest = {r.activity_id: r for r in ps_svc.list_latest(db, scene.head_u, scene.project.id)}
    assert set(latest) == {scene.activity.id, scene.other_activity.id}
    assert latest[scene.activity.id].tag_count == 140
    assert latest[scene.other_activity.id].tag_count == 500

    # And each activity's history contains only its own updates.
    fmtl_hist = ps_svc.list_history(
        db, scene.head_u, scene.project.id, activity_id=scene.activity.id
    )
    mtl_hist = ps_svc.list_history(
        db, scene.head_u, scene.project.id, activity_id=scene.other_activity.id
    )
    assert {r.activity_id for r in fmtl_hist} == {scene.activity.id}
    assert {r.activity_id for r in mtl_hist} == {scene.other_activity.id}
    assert [r.tag_count for r in fmtl_hist] == [140, 120]
    assert [r.id for r in mtl_hist] == [mtl.id]
    assert fmtl.id in {r.id for r in fmtl_hist}


# --- 15. multiple authors ----------------------------------------------------

def test_each_update_keeps_its_own_author(db, scene):
    """Two people working the same project keep their own names on their own
    updates - and on a shared trail, every entry keeps the person who made it."""
    # FMTL is updated by its Activity Lead, MTL by the Project Head.
    lead_out = ps_svc.create_production_status(
        db, scene.lead_u, scene.project.id, _payload(scene.activity.id, tag_count=120)
    )
    head_out = ps_svc.create_production_status(
        db, scene.head_u, scene.project.id,
        _payload(scene.other_activity.id, tag_count=500),
    )
    assert lead_out.created_by_name == "Santhosh Kumar"
    assert head_out.created_by_name == "Hema Rao"

    # The same activity updated by two different authorized people: both names
    # survive in the trail, in order.
    ps_svc.create_production_status(
        db, scene.head_u, scene.project.id, _payload(scene.activity.id, tag_count=225)
    )
    trail = ps_svc.list_history(
        db, scene.head_u, scene.project.id, activity_id=scene.activity.id
    )
    assert [r.created_by_name for r in trail] == ["Hema Rao", "Santhosh Kumar"]
    assert [r.created_by for r in trail] == [scene.head_u.id, scene.lead_u.id]

    # The role is never the author, at any layer.
    for r in trail:
        assert r.created_by_name not in {"Activity Lead", "Project Head", "PM", "Head"}


# --- 16. no de-duplication ---------------------------------------------------

def test_identical_updates_both_recorded(db, scene):
    """Two INTENTIONAL updates with identical values are legitimate history.

    Double-click protection lives in the UI (a disabled button), deliberately
    NOT in a uniqueness constraint - a constraint would refuse the second of two
    genuine updates, which is a worse failure than a rare duplicate row.
    """
    first = ps_svc.create_production_status(
        db, scene.head_u, scene.project.id, _payload(scene.activity.id, tag_count=225)
    )
    second = ps_svc.create_production_status(
        db, scene.head_u, scene.project.id, _payload(scene.activity.id, tag_count=225)
    )
    assert first.id != second.id
    assert db.query(ProjectProductionStatus).count() == 2

    trail = ps_svc.list_history(
        db, scene.head_u, scene.project.id, activity_id=scene.activity.id
    )
    assert len(trail) == 2
    # Exactly one of them is current, and it is deterministic.
    latest = ps_svc.list_latest(db, scene.head_u, scene.project.id)
    assert len(latest) == 1
    assert latest[0].id == trail[0].id

    # No unique index exists over the natural key that would have blocked this.
    uniques = {
        r[0] for r in db.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'project_production_statuses' "
                "AND indexdef LIKE '%UNIQUE%'"
            )
        ).all()
    }
    assert uniques == {"project_production_statuses_pkey"}


# --- 17. completed_on is a calendar date -------------------------------------

def test_completed_on_is_a_calendar_date(db, scene):
    """Stored as DATE, so no timezone can move it to the previous day."""
    out = ps_svc.create_production_status(
        db, scene.head_u, scene.project.id,
        _payload(scene.activity.id, status="closed", completed_on=date(2025, 12, 5)),
    )
    assert out.completed_on == date(2025, 12, 5)

    stored = db.execute(
        text("SELECT completed_on FROM project_production_statuses WHERE id = :i"),
        {"i": out.id},
    ).scalar_one()
    assert stored == date(2025, 12, 5)
    assert not hasattr(stored, "tzinfo")

    # Re-read through the API shape - still the 5th.
    latest = ps_svc.list_latest(db, scene.head_u, scene.project.id)
    assert latest[0].completed_on.isoformat() == "2025-12-05"

    # IN PROGRESS needs no completion date, and none is invented for it.
    later = ps_svc.create_production_status(
        db, scene.head_u, scene.project.id,
        _payload(scene.activity.id, revision="REV-1", status="in_progress"),
    )
    assert later.completed_on is None


# --- 18. multiline remarks ---------------------------------------------------

def test_multiline_remarks_are_preserved(db, scene):
    remark = "FMTL submitted to QE.\nAwaiting response.\nPunch list received."
    out = ps_svc.create_production_status(
        db, scene.head_u, scene.project.id,
        _payload(scene.activity.id, remarks=f"\n{remark}\n"),
    )
    # Surrounding whitespace is trimmed; the line breaks INSIDE are not.
    assert out.remarks == remark
    assert out.remarks.count("\n") == 2
    assert db.get(ProjectProductionStatus, out.id).remarks == remark

    # A blank remark is stored as NULL rather than an empty string.
    blank = ps_svc.create_production_status(
        db, scene.head_u, scene.project.id,
        _payload(scene.activity.id, revision="REV-1", remarks="   "),
    )
    assert blank.remarks is None


# --- 19. append-only: nothing can edit or delete -----------------------------

def test_module_exposes_no_update_or_delete(db, scene):
    """The append-only guarantee is structural, not a convention."""
    from app.modules.production_status import router as ps_router

    methods = set()
    for route in ps_router.router.routes:
        methods |= set(getattr(route, "methods", set()))
    assert methods == {"GET", "POST"}
    assert not (methods & {"PUT", "PATCH", "DELETE"})

    # No service function offers one either.
    assert not [n for n in dir(ps_svc) if n.startswith(("update_", "delete_", "edit_"))]

    # The table carries no updated_at / deleted_at to make an in-place edit
    # expressible in the first place.
    cols = {
        r[0] for r in db.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'project_production_statuses'"
            )
        ).all()
    }
    assert "updated_at" not in cols
    assert "deleted_at" not in cols

# ===========================================================================
# Phase 6 - the Head's activity list, PM read-only, and a typed activity.
# ===========================================================================

# --- 20. the PM is read-only -------------------------------------------------

def test_project_manager_cannot_record(db, scene, client, login):
    """Deliberate: production status is a claim about work that was done, made
    by the people who did it. The PM reads it - including the cumulative report
    nobody else can - and records none of it."""
    with pytest.raises(AppError) as ei:
        ps_svc.create_production_status(
            db, scene.pm, scene.project.id, _payload(scene.activity.id)
        )
    assert ei.value.status_code == 403

    # Over HTTP too, so it is not merely a service-level rule.
    res = client.post(
        f"/api/v1/projects/{scene.project.id}/production-status",
        headers=login("pm@x.com"),
        json={"revision": "REV-0", "activity_id": str(scene.activity.id),
              "status": "in_progress", "tag_count": 5},
    )
    assert res.status_code == 403


def test_the_pm_keeps_every_read(db, scene, client, login):
    """Read access is untouched - only the write is gone."""
    ps_svc.create_production_status(
        db, scene.head_u, scene.project.id, _payload(scene.activity.id, tag_count=225)
    )

    assert len(ps_svc.list_latest(db, scene.pm, scene.project.id)) == 1
    assert len(ps_svc.list_history(db, scene.pm, scene.project.id)) == 1
    # And the cumulative report is still PM-only.
    assert ps_svc.cumulative_report(db, scene.pm)["row_count"] == 1

    hdr = login("pm@x.com")
    base = f"/api/v1/projects/{scene.project.id}/production-status"
    assert client.get(base, headers=hdr).status_code == 200
    assert client.get(f"{base}/history", headers=hdr).status_code == 200


# --- 21. the Head reaches every Activity Master activity ---------------------

def test_head_may_record_against_an_unstaffed_activity(db, scene):
    """The change this phase exists for.

    An activity no one is staffed on is still an activity the project produces
    against, and the Head owns that output. Requiring staffing left a project
    with none unable to record anything at all.
    """
    unstaffed = _activity(db, "1ST STAGE IDB")

    out = ps_svc.create_production_status(
        db, scene.head_u, scene.project.id, _payload(unstaffed.id, tag_count=2136)
    )
    assert out.activity_name == "1ST STAGE IDB"
    assert out.tag_count == 2136

    # It appears on the tab and in the report like any other row.
    assert {r.activity_name for r in ps_svc.list_latest(db, scene.head_u, scene.project.id)} == {
        "1ST STAGE IDB"
    }


def test_a_lead_is_still_confined_to_the_activity_they_lead(db, scene):
    """Widening the Head's list did not widen anyone else's."""
    unstaffed = _activity(db, "1ST STAGE IDB")

    # Their own activity: fine.
    ps_svc.create_production_status(
        db, scene.lead_u, scene.project.id, _payload(scene.activity.id, tag_count=10)
    )
    # Another activity on the project, and one on no project at all: neither.
    for activity_id in (scene.other_activity.id, unstaffed.id):
        with pytest.raises(AppError) as ei:
            ps_svc.create_production_status(
                db, scene.lead_u, scene.project.id, _payload(activity_id)
            )
        assert ei.value.status_code == 403


# --- 22. a typed activity ----------------------------------------------------

def test_head_can_type_an_activity_that_is_not_in_activity_master(db, scene):
    out = ps_svc.create_production_status(
        db, scene.head_u, scene.project.id,
        ProductionStatusCreate(
            revision="REV-0", activity_label="HIERARCHY QA/QC",
            status="in_progress", tag_count=1654, doc_count=56,
        ),
    )

    assert out.activity_id is None
    assert out.activity_label == "HIERARCHY QA/QC"
    # Resolved to ONE name, so a client renders it without knowing which kind.
    assert out.activity_name == "HIERARCHY QA/QC"
    assert out.tag_count == 1654


def test_a_typed_activity_never_enters_activity_master(db, scene):
    """The whole reason it is a column and not a new master row: Activity
    Master drives work reports, staffing and benchmarks company-wide."""
    before = {a.id for a in am_svc.list_activities(db, active_only=False)}

    ps_svc.create_production_status(
        db, scene.head_u, scene.project.id,
        ProductionStatusCreate(revision="REV-0", activity_label="HIERARCHY QA/QC",
                               status="in_progress"),
    )

    assert {a.id for a in am_svc.list_activities(db, active_only=False)} == before


def test_a_typed_activity_has_its_own_identity_and_history(db, scene):
    """It supersedes and accumulates exactly as a master activity does."""
    for tag in (100, 200):
        ps_svc.create_production_status(
            db, scene.head_u, scene.project.id,
            ProductionStatusCreate(revision="REV-0", activity_label="HIERARCHY QA/QC",
                                   status="in_progress", tag_count=tag),
        )
    # A DIFFERENT typed name is a different row, not a newer version of the same.
    ps_svc.create_production_status(
        db, scene.head_u, scene.project.id,
        ProductionStatusCreate(revision="REV-0", activity_label="BOM QA/QC",
                               status="in_progress", tag_count=584),
    )
    # And so is a master activity, which must not collide with either.
    ps_svc.create_production_status(
        db, scene.head_u, scene.project.id, _payload(scene.activity.id, tag_count=7)
    )

    latest = ps_svc.list_latest(db, scene.head_u, scene.project.id)
    assert {(r.activity_name, r.tag_count) for r in latest} == {
        ("HIERARCHY QA/QC", 200), ("BOM QA/QC", 584), ("FMTL", 7),
    }

    # The trail is filterable by the typed name, the way an id filters a master
    # activity's - so a typed activity's History dialog shows only its own.
    trail = ps_svc.list_history(
        db, scene.head_u, scene.project.id, activity_label="HIERARCHY QA/QC"
    )
    assert [h.tag_count for h in trail] == [200, 100]


def test_only_the_head_may_type_an_activity(db, scene):
    """A Lead's authority is over ONE named Activity Master activity - a typed
    name has nothing for it to attach to."""
    for actor in (scene.lead_u, scene.other_u, scene.pm):
        with pytest.raises(AppError) as ei:
            ps_svc.create_production_status(
                db, actor, scene.project.id,
                ProductionStatusCreate(revision="REV-0", activity_label="TYPED",
                                       status="in_progress"),
            )
        assert ei.value.status_code == 403


def test_an_activity_is_named_exactly_once(db, scene):
    """Both, or neither, is refused before it reaches the database."""
    import pydantic

    # Neither.
    with pytest.raises(pydantic.ValidationError):
        ProductionStatusCreate(revision="REV-0", status="in_progress")
    # Both.
    with pytest.raises(pydantic.ValidationError):
        ProductionStatusCreate(
            revision="REV-0", activity_id=scene.activity.id,
            activity_label="TYPED", status="in_progress",
        )
    # Whitespace is not a name.
    with pytest.raises(pydantic.ValidationError):
        ProductionStatusCreate(revision="REV-0", activity_label="   ",
                               status="in_progress")

    # ...and the database refuses it too, so no other path can write one.
    with pytest.raises(Exception):
        db.execute(
            text(
                "INSERT INTO project_production_statuses "
                "(project_id, revision, status, created_by) "
                "VALUES (:p, 'REV-0', 'in_progress', :u)"
            ),
            {"p": str(scene.project.id), "u": str(scene.head_u.id)},
        )
    db.rollback()


def test_a_typed_name_is_stored_trimmed(db, scene):
    out = ps_svc.create_production_status(
        db, scene.head_u, scene.project.id,
        ProductionStatusCreate(revision="REV-0", activity_label="  PM PREPARATION  ",
                               status="in_progress"),
    )
    assert out.activity_label == "PM PREPARATION"
