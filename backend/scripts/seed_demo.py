"""Idempotent demo-data seed for local development / trying the UI.

Creates a manager and an employee (each linked to an Employee record), two active
projects with both as members, and one already-submitted work report awaiting the
manager's review — enough to walk the full Daily Work Reports flow in the UI.

Safe to re-run (looks up by email / employee_code / project code / (employee,date)).
LOCAL ONLY — never run against a production database.

Usage (inside the backend container):
    python -m scripts.seed_demo
"""
import sys
from datetime import date, datetime, timezone

from sqlalchemy import select

from datetime import timedelta

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.employees.models import Employee, EmployeeStatus
from app.modules.projects.models import (
    Project,
    ProjectMember,
    ProjectMemberRole,
    ProjectStatus,
)
from app.modules.users.models import User, UserRole
from app.modules.work_reports.models import (
    DailyWorkReport,
    WorkReportStatus,
    WorkReportTask,
)

PASSWORD = "password123"


def _get_user(db, email, role):
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        user = User(email=email, password_hash=hash_password(PASSWORD), role=role)
        db.add(user)
        db.flush()
    return user


def _get_employee(db, code, first, last, *, user_id=None, manager_id=None,
                  department=None, designation=None):
    emp = db.execute(
        select(Employee).where(Employee.employee_code == code)
    ).scalar_one_or_none()
    if emp is None:
        emp = Employee(
            employee_code=code,
            first_name=first,
            last_name=last,
            user_id=user_id,
            manager_id=manager_id,
            department=department,
            designation=designation,
            status=EmployeeStatus.active,
        )
        db.add(emp)
        db.flush()
    return emp


def _get_project(db, code, name, client=None):
    proj = db.execute(select(Project).where(Project.code == code)).scalar_one_or_none()
    if proj is None:
        proj = Project(code=code, name=name, client=client, status=ProjectStatus.active)
        db.add(proj)
        db.flush()
    return proj


def _ensure_member(db, project_id, employee_id, role):
    member = db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.employee_id == employee_id,
        )
    ).scalar_one_or_none()
    if member is None:
        db.add(ProjectMember(project_id=project_id, employee_id=employee_id, role=role))
        db.flush()


def _seed_attendance(db, employee_id):
    """Seed ~3 weeks of attendance up to today (weekdays only) for a calendar demo."""
    today = date.today()
    # A couple of non-present days for variety, keyed by offset-from-today.
    special = {9: AttendanceStatus.leave, 4: AttendanceStatus.half_day}
    for back in range(0, 22):
        day = today - timedelta(days=back)
        if day.weekday() >= 5:  # Sat/Sun — calendar infers these
            continue
        exists = db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.employee_id == employee_id,
                AttendanceRecord.attendance_date == day,
            )
        ).scalar_one_or_none()
        if exists:
            continue
        status = special.get(back, AttendanceStatus.present)
        if status == AttendanceStatus.present:
            check_in = datetime(day.year, day.month, day.day, 9, 5, tzinfo=timezone.utc)
            check_out = datetime(day.year, day.month, day.day, 18, 12, tzinfo=timezone.utc)
            total = int((check_out - check_in).total_seconds() // 60) - 60  # minus lunch
        elif status == AttendanceStatus.half_day:
            check_in = datetime(day.year, day.month, day.day, 9, 10, tzinfo=timezone.utc)
            check_out = datetime(day.year, day.month, day.day, 13, 30, tzinfo=timezone.utc)
            total = int((check_out - check_in).total_seconds() // 60)
        else:  # leave
            check_in = check_out = None
            total = 0
        db.add(AttendanceRecord(
            employee_id=employee_id,
            attendance_date=day,
            status=status,
            total_minutes=total,
            overtime_minutes=0,
            check_in_at=check_in,
            check_out_at=check_out,
        ))


def main() -> int:
    db = SessionLocal()
    try:
        mgr_user = _get_user(db, "manager@wms.local", UserRole.manager)
        emp_user = _get_user(db, "employee@wms.local", UserRole.employee)

        mgr_emp = _get_employee(
            db, "MGR-001", "Maya", "Manager",
            user_id=mgr_user.id, department="Engineering", designation="Engineering Manager",
        )
        emp_emp = _get_employee(
            db, "EMP-001", "Evan", "Employee",
            user_id=emp_user.id, manager_id=mgr_emp.id,
            department="Engineering", designation="Software Engineer",
        )

        apollo = _get_project(db, "PRJ-001", "Apollo", client="Acme")
        borealis = _get_project(db, "PRJ-002", "Borealis", client="Globex")
        for proj in (apollo, borealis):
            _ensure_member(db, proj.id, mgr_emp.id, ProjectMemberRole.lead)
            _ensure_member(db, proj.id, emp_emp.id, ProjectMemberRole.member)

        existing = db.execute(
            select(DailyWorkReport).where(
                DailyWorkReport.employee_id == emp_emp.id,
                DailyWorkReport.report_date == date.today(),
            )
        ).scalar_one_or_none()
        if existing is None:
            report = DailyWorkReport(
                employee_id=emp_emp.id,
                report_date=date.today(),
                status=WorkReportStatus.submitted,
                summary="Worked across Apollo and Borealis.",
                total_minutes=360,
                submitted_at=datetime.now(timezone.utc),
                created_by=emp_user.id,
                updated_by=emp_user.id,
            )
            db.add(report)
            db.flush()
            db.add(WorkReportTask(
                report_id=report.id, project_id=apollo.id,
                description="Implemented the login flow", minutes_spent=180,
            ))
            db.add(WorkReportTask(
                report_id=report.id, project_id=borealis.id,
                description="Fixed the report export bug", minutes_spent=180,
            ))

        _seed_attendance(db, emp_emp.id)

        db.commit()
        print("Demo seed complete. Logins (password: password123):")
        print("  manager@wms.local   manager  (MGR-001 Maya Manager)")
        print("  employee@wms.local  employee (EMP-001 Evan Employee, reports to MGR-001)")
        print("  admin@wms.local     admin    (existing; reviews everything)")
        print("Projects: Apollo (PRJ-001), Borealis (PRJ-002) — both active; both seeded users are members.")
        print("Seeded 1 SUBMITTED report for today, awaiting the manager's review.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
