"""The PM 'Employee performance' roster lists report-authoring staff only.
Managerial roles (project_manager / manager) never submit work reports, so they
carry no benchmark data and must not appear in the comparison table."""
from app.modules.benchmarks.service import get_employees_performance
from app.modules.users.models import UserRole


def test_performance_roster_excludes_managers(db, make_user, make_employee):
    pm = make_user("pm@x.com", role=UserRole.project_manager)
    make_employee(employee_code="MGR-1", user_id=pm.id, first_name="Alex", last_name="Manager")
    mgr = make_user("mgr@x.com", role=UserRole.manager)
    make_employee(employee_code="MGR-2", user_id=mgr.id, first_name="Pat", last_name="Lead")
    emp = make_user("e@x.com", role=UserRole.employee)
    make_employee(employee_code="E-1", user_id=emp.id, first_name="Reg", last_name="Employee")

    res = get_employees_performance(db, page=1, page_size=50)
    codes = {r["employee_code"] for r in res["items"]}

    assert "E-1" in codes              # report-authoring employee stays
    assert "MGR-1" not in codes        # project_manager excluded
    assert "MGR-2" not in codes        # manager excluded
