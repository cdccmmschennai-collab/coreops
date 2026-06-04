"""Reset all users and seed exactly three role accounts.

Wipes every user, employee, attendance, leave, project, and work-report row,
then creates three clean accounts — one per role — each with a linked Employee
profile so every feature works immediately.

Credentials after reset
-----------------------
  admin@coreops.local     Admin@123     Admin
  manager@coreops.local   Manager@123   Manager   (employee MGR-001)
  employee@coreops.local  Employee@123  Employee  (employee EMP-001, reports to manager)

LOCAL ONLY — never run against a production database.

Usage (inside the backend container):
    python -m scripts.seed_roles
"""
import sys

from sqlalchemy import text

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.modules.calendar.models import CalendarEvent  # noqa: F401 — registers mapper
from app.modules.employees.models import Employee, EmployeeStatus
from app.modules.offices.models import Office  # noqa: F401 — resolves employees.office_id FK
from app.modules.users.models import User, UserRole


ACCOUNTS = [
    {
        "email": "admin@coreops.local",
        "password": "Admin@123",
        "role": UserRole.admin,
        "employee": None,
    },
    {
        "email": "manager@coreops.local",
        "password": "Manager@123",
        "role": UserRole.manager,
        "employee": {
            "code": "MGR-001",
            "first": "Alex",
            "last": "Manager",
            "department": "Engineering",
            "designation": "Engineering Manager",
        },
    },
    {
        "email": "employee@coreops.local",
        "password": "Employee@123",
        "role": UserRole.employee,
        "employee": {
            "code": "EMP-001",
            "first": "Sam",
            "last": "Employee",
            "department": "Engineering",
            "designation": "Software Engineer",
        },
    },
]


def _wipe(db) -> None:
    """Delete all application data in FK-safe order."""
    db.execute(text("DELETE FROM work_report_tasks"))
    db.execute(text("DELETE FROM daily_work_reports"))
    db.execute(text("DELETE FROM leave_requests"))
    db.execute(text("DELETE FROM attendance_records"))
    db.execute(text("DELETE FROM project_members"))
    db.execute(text("DELETE FROM projects"))
    db.execute(text("DELETE FROM company_calendar_events"))
    # Clear manager FK before deleting employees to avoid FK cycle
    db.execute(text("UPDATE employees SET manager_id = NULL"))
    db.execute(text("DELETE FROM employees"))
    db.execute(text("DELETE FROM users"))
    db.flush()
    print("  wiped all existing data")


def main() -> int:
    db = SessionLocal()
    try:
        print("Resetting database …")
        _wipe(db)

        manager_emp = None

        for acc in ACCOUNTS:
            user = User(
                email=acc["email"],
                password_hash=hash_password(acc["password"]),
                role=acc["role"],
            )
            db.add(user)
            db.flush()

            if acc["employee"]:
                e = acc["employee"]
                emp = Employee(
                    employee_code=e["code"],
                    first_name=e["first"],
                    last_name=e["last"],
                    user_id=user.id,
                    department=e["department"],
                    designation=e["designation"],
                    status=EmployeeStatus.active,
                )
                db.add(emp)
                db.flush()

                if acc["role"] == UserRole.manager:
                    manager_emp = emp
                elif acc["role"] == UserRole.employee and manager_emp:
                    emp.manager_id = manager_emp.id
                    db.flush()

        db.commit()
        print("\nDone. Login credentials:")
        print()
        print("  Role      Email                    Password")
        print("  --------  -----------------------  ------------")
        for acc in ACCOUNTS:
            print(f"  {acc['role'].value:<8}  {acc['email']:<23}  {acc['password']}")
        print()
        print("Employee profiles:")
        print("  MGR-001  Alex Manager   (manager@coreops.local)")
        print("  EMP-001  Sam Employee   (employee@coreops.local, reports to MGR-001)")
        print()
        print("Admin has no employee profile — manages the system, not team tasks.")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
