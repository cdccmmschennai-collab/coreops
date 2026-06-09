"""Task service: PM creates/assigns; employees update status on own tasks.

RBAC (this module):
  project_manager  create, edit, cancel, view all tasks
  employee         view own assigned tasks, update status (open/in_progress/completed)
"""
import uuid
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.modules.employees.models import Employee, EmployeeStatus
from app.modules.employees.service import _current_employee
from app.modules.tasks.models import Task, TaskPriority, TaskStatus
from app.modules.tasks.schemas import TaskCreate, TaskStatusUpdate, TaskUpdate
from app.modules.users.models import User, UserRole
from app.shared.errors import AppError

_EMPLOYEE_ALLOWED_STATUSES = {
    TaskStatus.open,
    TaskStatus.in_progress,
    TaskStatus.completed,
}


def _push_notification(
    db: Session,
    user_id: uuid.UUID,
    type_: str,
    title: str,
    message: str,
    entity_id: uuid.UUID | None = None,
    target_url: str | None = None,
) -> None:
    try:
        from app.modules.notifications.service import create_notification

        create_notification(
            db,
            user_id=user_id,
            type_=type_,
            title=title,
            message=message,
            entity_type="task",
            entity_id=entity_id,
            target_url=target_url,
        )
        db.commit()
    except Exception:
        db.rollback()


def _pm_employee(db: Session, actor: User) -> Employee:
    me = _current_employee(db, actor)
    if me is None:
        raise AppError(
            "validation_error",
            "You need an employee profile to assign tasks.",
            422,
        )
    return me


def _fetch_assignee(db: Session, employee_id: uuid.UUID) -> Employee:
    assignee = db.execute(
        select(Employee).where(Employee.id == employee_id, Employee.deleted_at.is_(None))
    ).scalar_one_or_none()
    if assignee is None:
        raise AppError("not_found", "Assignee employee not found.", 404)
    if assignee.status != EmployeeStatus.active:
        raise AppError("validation_error", "Tasks can only be assigned to active employees.", 422)
    if assignee.user_id is None:
        raise AppError(
            "validation_error",
            "Assignee must have a linked user account.",
            422,
        )
    user = db.get(User, assignee.user_id)
    if user is None or user.role != UserRole.employee:
        raise AppError(
            "validation_error",
            "Tasks can only be assigned to employees.",
            422,
        )
    return assignee


def _fetch(db: Session, task_id: uuid.UUID) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise AppError("not_found", "Task not found.", 404)
    return task


def _assert_can_read(db: Session, actor: User, task: Task) -> None:
    if actor.role == UserRole.project_manager:
        return
    me = _current_employee(db, actor)
    if me is None or task.assigned_to_employee_id != me.id:
        raise AppError("forbidden", "You can only view tasks assigned to you.", 403)


def list_tasks(
    db: Session,
    actor: User,
    *,
    mine: bool,
    q: str | None,
    status: TaskStatus | None,
    priority: TaskPriority | None,
    due_from: date | None,
    due_to: date | None,
    limit: int,
    offset: int,
) -> tuple[list[Task], int]:
    stmt = select(Task)

    if actor.role == UserRole.employee:
        me = _current_employee(db, actor)
        if me is None:
            return [], 0
        stmt = stmt.where(Task.assigned_to_employee_id == me.id)
    elif mine:
        me = _current_employee(db, actor)
        if me is None:
            return [], 0
        stmt = stmt.where(Task.assigned_to_employee_id == me.id)

    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Task.title.ilike(like), Task.description.ilike(like)))
    if status is not None:
        stmt = stmt.where(Task.status == status)
    if priority is not None:
        stmt = stmt.where(Task.priority == priority)
    if due_from is not None:
        stmt = stmt.where(Task.due_date >= due_from)
    if due_to is not None:
        stmt = stmt.where(Task.due_date <= due_to)

    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = (
        db.execute(
            stmt.options(
                selectinload(Task.assigned_to), selectinload(Task.assigned_by)
            )
            .order_by(Task.due_date.asc().nulls_last(), Task.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return list(rows), total


def get_task(db: Session, actor: User, task_id: uuid.UUID) -> Task:
    task = _fetch(db, task_id)
    _assert_can_read(db, actor, task)
    return task


def create_task(db: Session, actor: User, body: TaskCreate) -> Task:
    pm = _pm_employee(db, actor)
    assignee = _fetch_assignee(db, body.assigned_to_employee_id)

    task = Task(
        title=body.title.strip(),
        description=body.description.strip() if body.description else None,
        assigned_to_employee_id=assignee.id,
        assigned_by_employee_id=pm.id,
        status=TaskStatus.open,
        priority=body.priority,
        due_date=body.due_date,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    if assignee.user_id is not None:
        _push_notification(
            db,
            assignee.user_id,
            "task_assigned",
            "New task assigned",
            f"Task: {task.title}",
            entity_id=task.id,
            target_url=f"/tasks/{task.id}",
        )

    return task


def update_task(db: Session, actor: User, task_id: uuid.UUID, body: TaskUpdate) -> Task:
    task = _fetch(db, task_id)

    if actor.role != UserRole.project_manager:
        raise AppError("forbidden", "Only project managers can edit tasks.", 403)

    if body.title is not None:
        task.title = body.title.strip()
    if body.description is not None:
        task.description = body.description.strip() or None
    if body.priority is not None:
        task.priority = body.priority
    if body.due_date is not None or "due_date" in body.model_fields_set:
        task.due_date = body.due_date
    if body.assigned_to_employee_id is not None:
        assignee = _fetch_assignee(db, body.assigned_to_employee_id)
        if assignee.id != task.assigned_to_employee_id:
            task.assigned_to_employee_id = assignee.id
            if assignee.user_id is not None:
                _push_notification(
                    db,
                    assignee.user_id,
                    "task_assigned",
                    "New task assigned",
                    f"Task: {task.title}",
                    entity_id=task.id,
                    target_url=f"/tasks/{task.id}",
                )
    if body.status is not None:
        task.status = body.status

    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def update_task_status(
    db: Session, actor: User, task_id: uuid.UUID, body: TaskStatusUpdate
) -> Task:
    task = _fetch(db, task_id)
    me = _current_employee(db, actor)
    if me is None or task.assigned_to_employee_id != me.id:
        raise AppError("forbidden", "You can only update tasks assigned to you.", 403)
    if task.status == TaskStatus.cancelled:
        raise AppError("validation_error", "Cancelled tasks cannot be updated.", 422)
    if body.status not in _EMPLOYEE_ALLOWED_STATUSES:
        raise AppError("validation_error", "You cannot set that status.", 422)
    if task.status == TaskStatus.completed and body.status != TaskStatus.completed:
        raise AppError("validation_error", "Completed tasks cannot be reopened.", 422)

    task.status = body.status
    db.add(task)
    db.commit()
    db.refresh(task)
    return task
