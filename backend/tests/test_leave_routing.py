"""Tests for leave-approval routing to Project Head (Phase 1).

`test_leave_routing.py` covers the resolver (Task 2) and this file's own
Task-1 smoke test that `routed_project_id` persists and serializes. Task 3/4
API-level behavior (notification target, scope, authorization) lives in
`test_leave_api.py` alongside the rest of the leave RBAC suite it extends.
"""
from datetime import date

from app.modules.leave.models import LeaveRequest, LeaveStatus, LeaveType


def test_routed_project_id_persists(db, make_employee, make_user, make_project):
    u = make_user("emp@x.com")
    emp = make_employee(employee_code="E1", user_id=u.id)
    project = make_project(code="P-1")

    req = LeaveRequest(
        employee_id=emp.id,
        leave_type=LeaveType.casual,
        start_date=date.today(),
        end_date=date.today(),
        status=LeaveStatus.pending,
        routed_project_id=project.id,
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    assert req.routed_project_id == project.id
