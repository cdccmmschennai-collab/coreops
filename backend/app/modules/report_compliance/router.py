"""Daily Report Compliance endpoints.

  GET  /report-compliance/me   own snapshot (attendance vs submitted report)

Read-only over existing data; drives the employee 5:15 reminder, the login
pending-reports banner, and the logout guard.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.report_compliance import service
from app.modules.report_compliance.schemas import EmployeeComplianceOut
from app.modules.users.models import User

router = APIRouter(prefix="/report-compliance", tags=["report-compliance"])


@router.get("/me", response_model=EmployeeComplianceOut)
def my_compliance(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EmployeeComplianceOut:
    return EmployeeComplianceOut.model_validate(
        service.employee_compliance(db, current)
    )
