"""Production Status endpoints.

Per project (Phase 1 - the minimum Phase 2 needs):

  GET  /projects/{project_id}/production-status          latest per revision+activity
  GET  /projects/{project_id}/production-status/history  full trail (filterable)
  POST /projects/{project_id}/production-status          append one update

Cumulative, across every project (Phase 4 - the PM report):

  GET  /production-status/report        the whole report as JSON (PM only)
  GET  /production-status/report.xlsx   the SAME dataset as .xlsx (PM only)

Both take one optional `?month=YYYY-MM`, and both pass it to the same service
call, so the download is always the preview's rows.

No PATCH / PUT / DELETE by design: production status is append-only history, so
a correction is a new update, not an edit of an old one.

On the per-project routes the project is always taken from the path - it is what
the caller is authorized against, and it is what the plant information is
derived from. It is never accepted in a request body.

The report routes live on their own `/production-status` prefix rather than
under `/projects/{id}`, because the report is not about one project: it spans
all of them, and it is authorized by role alone.
"""
import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.production_status import service
from app.modules.production_status.schemas import (
    ProductionStatusCreate,
    ProductionStatusOut,
    ProductionStatusReportOut,
)
from app.modules.reports_export import export
from app.modules.users.models import User

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

router = APIRouter(prefix="/projects", tags=["production-status"])

# The cumulative report. A second APIRouter only because the path prefix
# differs; both are registered in main.py and both hang off the same service.
report_router = APIRouter(prefix="/production-status", tags=["production-status"])


@router.get("/{project_id}/production-status", response_model=list[ProductionStatusOut])
def list_latest_production_status(
    project_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ProductionStatusOut]:
    return service.list_latest(db, current, project_id)


@router.get(
    "/{project_id}/production-status/history",
    response_model=list[ProductionStatusOut],
)
def list_production_status_history(
    project_id: uuid.UUID,
    activity_id: uuid.UUID | None = Query(default=None),
    # The typed activity's own name, for a record that has no activity_id
    # (migration 0072). A caller sends whichever one the row carries.
    activity_label: str | None = Query(default=None),
    revision: str | None = Query(default=None),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ProductionStatusOut]:
    return service.list_history(
        db,
        current,
        project_id,
        activity_id=activity_id,
        activity_label=activity_label,
        revision=revision,
    )


@router.post(
    "/{project_id}/production-status",
    response_model=ProductionStatusOut,
    status_code=201,
)
def create_production_status(
    project_id: uuid.UUID,
    body: ProductionStatusCreate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProductionStatusOut:
    return service.create_production_status(db, current, project_id, body)


# ---------------------------------------------------------------------------
# Cumulative report - PM only
# ---------------------------------------------------------------------------


# The one optional narrowing both report routes accept. Declared once so the
# preview and the download cannot drift into accepting different filters - which
# is the whole reason the file always matches the screen.
_MONTH_QUERY = Query(
    default=None,
    description=(
        "Narrow the report to the production status records RECORDED in this "
        "month, as YYYY-MM (for example 2026-08). Omit it for the cumulative "
        "all-months report. The month is the record's created_at month, never "
        "completed_on - an in-progress record has no completion date."
    ),
)


@report_router.get("/report", response_model=ProductionStatusReportOut)
def get_production_status_report(
    month: str | None = _MONTH_QUERY,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProductionStatusReportOut:
    """The latest production status of every project + revision + activity.

    ONE request for the whole report - the client never walks the project list
    firing a request per project. The response also carries `months`, every
    month that has records, so the month picker needs no second request either.

    project_manager only, enforced inside the service (`_assert_can_read_report`)
    rather than by a role dependency here, so a Head, an activity Lead or an
    ordinary employee gets the same 403 whether they reach it through the API or
    through any other caller of the service. Hiding the button in the UI is
    convenience; this is the control. The month filter changes nothing about
    that rule - it narrows what a PM sees, it never widens who may see it.
    """
    return ProductionStatusReportOut.model_validate(
        service.cumulative_report(db, current, month=month)
    )


@report_router.get("/report.xlsx")
def get_production_status_report_xlsx(
    month: str | None = _MONTH_QUERY,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """The same dataset as the preview, as a styled .xlsx download.

    Calls the identical service function the preview does, with the identical
    `month` - one query, one ordering, one filter, one set of rows - so the file
    can never hold more or fewer rows than the screen it was downloaded from.
    Authorization runs again inside that service, so pasting this URL as a
    non-PM fails with 403 exactly as the preview does.

    `.xlsx` suffix + StreamingResponse + Content-Disposition is the established
    CoreOps export shape (/projects/{id}/weekly-report.xlsx,
    /reports-export/activity-rows.xlsx) - no second Excel stack, no base64 in
    JSON.
    """
    data = service.cumulative_report(db, current, month=month)
    # model_dump() so the workbook builder reads plain dicts, the same contract
    # build_project_weekly_report_workbook already has.
    payload = {
        **data,
        "rows": [row.model_dump() for row in data["rows"]],
    }
    buf = export.build_production_status_report_workbook(payload)
    # Named for the month when there is one, so two downloads taken on the same
    # day are told apart. `data["month"]` rather than the raw query value, so the
    # name describes the dataset that was actually built.
    filename = service.report_filename(month=data["month"])
    return StreamingResponse(
        buf,
        media_type=XLSX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
