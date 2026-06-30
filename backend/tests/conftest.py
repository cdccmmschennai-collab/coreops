"""Pytest fixtures.

Targets a dedicated `wms_test` database so tests never touch dev data. The test
DB URL is derived from DATABASE_URL and set BEFORE importing the app, so app
settings/engine and Alembic all point at the test database. Schema is created by
running the real migrations once; each test gets a clean slate (truncate + redis
flush).
"""
import os

import pytest

# --- redirect to the test database BEFORE importing the app ---------------
_base_url = os.environ.get("DATABASE_URL", "postgresql+psycopg://wms:wms@db:5432/wms")
_server, _db = _base_url.rsplit("/", 1)
_TEST_URL = f"{_server}/wms_test"
os.environ["DATABASE_URL"] = _TEST_URL
os.environ.setdefault("ENV", "local")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.core.redis import get_redis  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.attendance.models import AttendanceRecord, AttendanceStatus  # noqa: E402
from app.modules.employees.models import Employee, EmployeeStatus  # noqa: E402
from app.modules.leave.models import LeaveRequest, LeaveStatus, LeaveType  # noqa: E402
from app.modules.offices.models import Office  # noqa: E402
from app.modules.projects.models import (  # noqa: E402
    Project,
    ProjectMember,
    ProjectMemberRole,
    ProjectStatus,
)
from app.modules.users.models import User, UserRole  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _prepare_database():
    # Create wms_test if absent, then apply migrations.
    admin_engine = create_engine(_base_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = 'wms_test'")
        ).scalar()
        if not exists:
            conn.execute(text("CREATE DATABASE wms_test"))
    admin_engine.dispose()

    from alembic import command
    from alembic.config import Config

    command.upgrade(Config("alembic.ini"), "head")
    yield


@pytest.fixture(autouse=True)
def _clean_state():
    # Clean slate per test: empty tables, clear redis (throttle/denylist keys).
    with SessionLocal() as db:
        db.execute(
            text(
                "TRUNCATE TABLE audit_logs, notifications, tasks, work_report_tasks, "
                "daily_work_reports, attendance_records, leave_requests, "
                "project_managers, project_members, projects, company_calendar_events, "
                "activity_types, activity_master, maintenance_plants, planning_plants, "
                "job_codes, employees, offices, users "
                "RESTART IDENTITY CASCADE"
            )
        )
        db.commit()
    get_redis().flushdb()
    yield


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


# --- helpers ---------------------------------------------------------------
@pytest.fixture()
def make_user(db):
    def _make(email: str, password: str = "password123", role: UserRole = UserRole.employee,
              is_active: bool = True) -> User:
        user = User(
            email=email,
            password_hash=hash_password(password),
            role=role,
            is_active=is_active,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    return _make


@pytest.fixture()
def auth_header(client, make_user):
    def _login(email: str = "user@example.com", password: str = "password123",
               role: UserRole = UserRole.employee) -> dict:
        make_user(email, password, role)
        res = client.post("/api/v1/auth/login", json={"identifier": email, "password": password})
        assert res.status_code == 200, res.text
        return {"Authorization": f"Bearer {res.json()['access_token']}"}

    return _login


@pytest.fixture()
def login(client):
    """Log in an EXISTING user; returns the auth header."""

    def _login(email: str, password: str = "password123") -> dict:
        res = client.post("/api/v1/auth/login", json={"identifier": email, "password": password})
        assert res.status_code == 200, res.text
        return {"Authorization": f"Bearer {res.json()['access_token']}"}

    return _login


@pytest.fixture()
def make_employee(db):
    def _make(
        *,
        employee_code: str,
        first_name: str = "Test",
        last_name: str = "User",
        user_id=None,
        manager_id=None,
        status: EmployeeStatus = EmployeeStatus.active,
        department: str | None = None,
        designation: str | None = None,
        work_email: str | None = None,
    ) -> Employee:
        emp = Employee(
            employee_code=employee_code,
            first_name=first_name,
            last_name=last_name,
            user_id=user_id,
            manager_id=manager_id,
            status=status,
            department=department,
            designation=designation,
            work_email=work_email,
        )
        db.add(emp)
        db.commit()
        db.refresh(emp)
        return emp

    return _make


@pytest.fixture()
def make_project(db):
    def _make(
        *,
        code: str,
        name: str = "Test Project",
        client: str | None = None,
        status: ProjectStatus = ProjectStatus.planning,
        start_date=None,
        planned_completion_date=None,
        end_date=None,  # legacy alias
    ) -> Project:
        project = Project(
            code=code,
            name=name,
            client=client,
            status=status,
            start_date=start_date,
            planned_completion_date=planned_completion_date or end_date,
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        return project

    return _make


@pytest.fixture()
def make_project_member(db):
    def _make(
        *, project_id, employee_id, role: ProjectMemberRole = ProjectMemberRole.contributor
    ) -> ProjectMember:
        member = ProjectMember(
            project_id=project_id, employee_id=employee_id, role=role
        )
        db.add(member)
        db.commit()
        db.refresh(member)
        return member

    return _make


@pytest.fixture()
def make_office(db):
    def _make(
        *,
        name: str = "Test Office",
        timezone: str = "Asia/Kolkata",
        shift_start: str = "09:00",
        shift_end: str = "17:30",
        break_minutes: int = 30,
        is_active: bool = True,
    ) -> Office:
        from datetime import time as dtime
        h_s, m_s = map(int, shift_start.split(":"))
        h_e, m_e = map(int, shift_end.split(":"))
        office = Office(
            name=name,
            timezone=timezone,
            shift_start=dtime(h_s, m_s),
            shift_end=dtime(h_e, m_e),
            break_minutes=break_minutes,
            is_active=is_active,
        )
        db.add(office)
        db.commit()
        db.refresh(office)
        return office

    return _make


@pytest.fixture()
def make_leave_request(db):
    def _make(
        *,
        employee_id,
        leave_type: LeaveType = LeaveType.casual,
        start_date,
        end_date,
        reason: str | None = "Test reason",
        status: LeaveStatus = LeaveStatus.pending,
        manager_id=None,
        created_by=None,
    ) -> LeaveRequest:
        req = LeaveRequest(
            employee_id=employee_id,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            reason=reason,
            status=status,
            manager_id=manager_id,
            created_by=created_by,
            updated_by=created_by,
        )
        db.add(req)
        db.commit()
        db.refresh(req)
        return req

    return _make


@pytest.fixture()
def make_attendance(db):
    def _make(
        *,
        employee_id,
        attendance_date,
        status: AttendanceStatus = AttendanceStatus.present,
        total_minutes: int = 0,
        overtime_minutes: int = 0,
        check_in_at=None,
        check_out_at=None,
    ) -> AttendanceRecord:
        record = AttendanceRecord(
            employee_id=employee_id,
            attendance_date=attendance_date,
            status=status,
            total_minutes=total_minutes,
            overtime_minutes=overtime_minutes,
            check_in_at=check_in_at,
            check_out_at=check_out_at,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    return _make
