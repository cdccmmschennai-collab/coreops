"""Homepage Alerts endpoints.

  GET /benchmarks/my-alerts     employee's own shortfalls/overdue/summary (any authenticated user)
  GET /benchmarks/team-alerts   org-wide backlog/overdue/KPIs (project_manager only)

These back the existing homepage — no new dashboard page, no notification
tab. Everything is computed live from Phase 1's get_daily_benchmark_ledger
/ get_overdue_activities; nothing here is persisted or scheduled.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.modules.benchmarks import service
from app.modules.benchmarks.schemas import MyAlertsOut, TeamAlertsOut
from app.modules.users.models import User

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])

AuthUser = Depends(get_current_user)
PMUser = Depends(require_role("project_manager"))


@router.get("/my-alerts", response_model=MyAlertsOut)
def my_alerts(user: User = AuthUser, db: Session = Depends(get_db)) -> MyAlertsOut:
    return MyAlertsOut.model_validate(service.get_my_alerts(db, user))


@router.get("/team-alerts", response_model=TeamAlertsOut)
def team_alerts(_user: User = PMUser, db: Session = Depends(get_db)) -> TeamAlertsOut:
    return TeamAlertsOut.model_validate(service.get_team_alerts(db, _user))
