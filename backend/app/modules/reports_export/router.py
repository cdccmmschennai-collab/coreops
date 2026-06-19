"""PM Weekly Activity Report — preview + Excel export.

  GET /reports-export/activity-rows        flat Employee+Date preview (JSON)
  GET /reports-export/activity-rows.xlsx   styled .xlsx (weekly template)

Both share work_reports.service.build_activity_groups, so the preview shows
exactly what the export contains. RBAC matches the report list (PM = all
non-draft; team leads = led projects; others = own)."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.reports_export import export
from app.modules.reports_export.schemas import ActivityReportOut
from app.modules.users.models import User
from app.modules.work_reports import service

router = APIRouter(prefix="/reports-export", tags=["reports-export"])

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _groups(
    db: Session,
    current: User,
    employee_id: uuid.UUID | None,
    project_id: uuid.UUID | None,
    activity_id: uuid.UUID | None,
    sub_activity_id: uuid.UUID | None,
    date_from: date | None,
    date_to: date | None,
) -> dict:
    return service.build_activity_groups(
        db,
        current,
        employee_id=employee_id,
        project_id=project_id,
        activity_id=activity_id,
        sub_activity_id=sub_activity_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/activity-rows", response_model=ActivityReportOut)
def activity_rows(
    employee_id: uuid.UUID | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
    activity_id: uuid.UUID | None = Query(default=None),
    sub_activity_id: uuid.UUID | None = Query(default=None),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActivityReportOut:
    return ActivityReportOut.model_validate(
        _groups(db, current, employee_id, project_id, activity_id, sub_activity_id, date_from, date_to)
    )


@router.get("/activity-rows.xlsx")
def activity_rows_xlsx(
    employee_id: uuid.UUID | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
    activity_id: uuid.UUID | None = Query(default=None),
    sub_activity_id: uuid.UUID | None = Query(default=None),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    data = _groups(db, current, employee_id, project_id, activity_id, sub_activity_id, date_from, date_to)
    buf = export.build_workbook(data["rows"], data["max_activities"])
    filename = f"weekly-activity-report-{date.today().isoformat()}.xlsx"
    return StreamingResponse(
        buf,
        media_type=XLSX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
