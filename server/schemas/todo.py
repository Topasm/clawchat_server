from datetime import datetime

from pydantic import BaseModel


class TodoCreate(BaseModel):
    title: str
    description: str | None = None
    priority: str = "medium"
    due_date: datetime | None = None
    tags: list[str] | None = None
    parent_id: str | None = None
    sort_order: int | None = None
    source: str | None = None
    source_id: str | None = None
    assignee: str | None = None


class TodoUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    due_date: datetime | None = None
    tags: list[str] | None = None
    parent_id: str | None = None
    sort_order: int | None = None
    assignee: str | None = None


class TodoResponse(BaseModel):
    id: str
    title: str
    description: str | None = None
    status: str
    priority: str
    due_date: datetime | None = None
    completed_at: datetime | None = None
    tags: list[str] | None = None
    parent_id: str | None = None
    sort_order: int = 0
    source: str | None = None
    source_id: str | None = None
    assignee: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
