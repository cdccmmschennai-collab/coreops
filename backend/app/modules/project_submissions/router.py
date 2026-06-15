"""Project submission endpoints.

  GET    /projects/{id}/submissions
  POST   /projects/{id}/submissions               PM only
  GET    /projects/{id}/submissions/{sid}         PM + team lead
  PATCH  /projects/{id}/submissions/{sid}         PM only (draft only)
  DELETE /projects/{id}/submissions/{sid}         PM only (draft only)
  PATCH  /projects/{id}/submissions/{sid}/status  PM only
"""
import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.project_submissions import service
from app.modules.project_submissions.schemas import (
    SubmissionCreate,
    SubmissionOut,
    SubmissionStatusUpdate,
    SubmissionUpdate,
)
from app.modules.users.models import User

router = APIRouter(prefix="/projects", tags=["submissions"])


@router.get("/{project_id}/submissions", response_model=list[SubmissionOut])
def list_submissions(
    project_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SubmissionOut]:
    return [
        SubmissionOut.model_validate(s)
        for s in service.list_submissions(db, current, project_id)
    ]


@router.post("/{project_id}/submissions", response_model=SubmissionOut, status_code=201)
def create_submission(
    project_id: uuid.UUID,
    body: SubmissionCreate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SubmissionOut:
    return SubmissionOut.model_validate(
        service.create_submission(db, current, project_id, body)
    )


@router.get("/{project_id}/submissions/{submission_id}", response_model=SubmissionOut)
def get_submission(
    project_id: uuid.UUID,
    submission_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SubmissionOut:
    return SubmissionOut.model_validate(
        service.get_submission(db, current, project_id, submission_id)
    )


@router.patch("/{project_id}/submissions/{submission_id}", response_model=SubmissionOut)
def update_submission(
    project_id: uuid.UUID,
    submission_id: uuid.UUID,
    body: SubmissionUpdate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SubmissionOut:
    return SubmissionOut.model_validate(
        service.update_submission(db, current, project_id, submission_id, body)
    )


@router.patch(
    "/{project_id}/submissions/{submission_id}/status", response_model=SubmissionOut
)
def update_submission_status(
    project_id: uuid.UUID,
    submission_id: uuid.UUID,
    body: SubmissionStatusUpdate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SubmissionOut:
    return SubmissionOut.model_validate(
        service.update_submission_status(db, current, project_id, submission_id, body)
    )


@router.delete("/{project_id}/submissions/{submission_id}", status_code=204)
def delete_submission(
    project_id: uuid.UUID,
    submission_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    service.delete_submission(db, current, project_id, submission_id)
    return Response(status_code=204)
