"""Task pydantic schemas."""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.tasks.models import Task, TaskPriority, TaskStatus


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None = None
    assigned_to_employee_id: uuid.UUID
    assigned_by_employee_id: uuid.UUID
    assigned_to_name: str = ""
    assigned_by_name: str = ""
    status: TaskStatus
    priority: TaskPriority
    due_date: date | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_task(cls, task: Task) -> "TaskOut":
        """Serialize a Task ORM row, resolving assignee/assigner display names."""
        return cls(
            id=task.id,
            title=task.title,
            description=task.description,
            assigned_to_employee_id=task.assigned_to_employee_id,
            assigned_by_employee_id=task.assigned_by_employee_id,
            assigned_to_name=task.assigned_to.full_name if task.assigned_to else "",
            assigned_by_name=task.assigned_by.full_name if task.assigned_by else "",
            status=task.status,
            priority=task.priority,
            due_date=task.due_date,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    assigned_to_employee_id: uuid.UUID
    priority: TaskPriority = TaskPriority.medium
    due_date: date | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    assigned_to_employee_id: uuid.UUID | None = None
    priority: TaskPriority | None = None
    due_date: date | None = None
    status: TaskStatus | None = None


class TaskStatusUpdate(BaseModel):
    status: TaskStatus


class TaskPage(BaseModel):
    items: list[TaskOut]
    total: int
    limit: int
    offset: int
