"""Office endpoints — admin only.

  GET    /offices          list all offices (paginated)
  POST   /offices          create office
  GET    /offices/{id}     get office
  PATCH  /offices/{id}     update office
"""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role
from app.modules.offices import service
from app.modules.offices.schemas import OfficeCreate, OfficeOut, OfficePage, OfficeUpdate
from app.modules.users.models import User

router = APIRouter(prefix="/offices", tags=["offices"])

AdminUser = Depends(require_role("admin"))


@router.get("", response_model=OfficePage)
def list_offices(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _admin: User = AdminUser,
    db: Session = Depends(get_db),
) -> OfficePage:
    rows, total = service.list_offices(db, limit=limit, offset=offset)
    return OfficePage(
        items=[OfficeOut.model_validate(o) for o in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=OfficeOut, status_code=201)
def create_office(
    body: OfficeCreate,
    _admin: User = AdminUser,
    db: Session = Depends(get_db),
) -> OfficeOut:
    return OfficeOut.model_validate(service.create_office(db, body))


@router.get("/{office_id}", response_model=OfficeOut)
def get_office(
    office_id: uuid.UUID,
    _admin: User = AdminUser,
    db: Session = Depends(get_db),
) -> OfficeOut:
    return OfficeOut.model_validate(service.get_office(db, office_id))


@router.patch("/{office_id}", response_model=OfficeOut)
def update_office(
    office_id: uuid.UUID,
    body: OfficeUpdate,
    _admin: User = AdminUser,
    db: Session = Depends(get_db),
) -> OfficeOut:
    return OfficeOut.model_validate(service.update_office(db, office_id, body))
