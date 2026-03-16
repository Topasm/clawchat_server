"""Async service layer for todo CRUD operations."""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions import NotFoundError
from models.todo import Todo
from utils import apply_model_updates, make_id, serialize_tags


_ORDER_COLUMNS = {
    "created_at": Todo.created_at,
    "updated_at": Todo.updated_at,
    "sort_order": Todo.sort_order,
    "priority": Todo.priority,
}


async def get_todos(
    db: AsyncSession,
    *,
    status_filter: str | None = None,
    priority: str | None = None,
    due_before: datetime | None = None,
    parent_id: str | None = None,
    root_only: bool = False,
    order_by: str = "created_at",
    order_dir: str = "desc",
    page: int = 1,
    limit: int = 20,
) -> tuple[list[Todo], int]:
    conditions = []
    if status_filter is not None:
        conditions.append(Todo.status == status_filter)
    if priority is not None:
        conditions.append(Todo.priority == priority)
    if due_before is not None:
        conditions.append(Todo.due_date <= due_before)
    if parent_id is not None:
        conditions.append(Todo.parent_id == parent_id)
    if root_only:
        conditions.append(Todo.parent_id.is_(None))

    count_q = select(func.count(Todo.id)).where(*conditions)
    total = (await db.execute(count_q)).scalar() or 0

    col = _ORDER_COLUMNS.get(order_by, Todo.created_at)
    order_clause = col.asc() if order_dir == "asc" else col.desc()

    q = (
        select(Todo)
        .where(*conditions)
        .order_by(order_clause)
        .offset((page - 1) * limit)
        .limit(limit)
    )
    rows = (await db.execute(q)).scalars().all()
    return list(rows), total


async def get_todo(db: AsyncSession, todo_id: str) -> Todo:
    todo = await db.get(Todo, todo_id)
    if not todo:
        raise NotFoundError(f"Todo {todo_id} not found")
    return todo


async def create_todo(
    db: AsyncSession,
    *,
    title: str,
    description: str | None = None,
    priority: str = "medium",
    due_date: datetime | None = None,
    tags: list[str] | None = None,
    parent_id: str | None = None,
    sort_order: int = 0,
    source: str | None = None,
    source_id: str | None = None,
    assignee: str | None = None,
) -> Todo:
    todo = Todo(
        id=make_id("todo_"),
        title=title,
        description=description,
        priority=priority,
        due_date=due_date,
        tags=serialize_tags(tags),
        parent_id=parent_id,
        sort_order=sort_order,
        source=source,
        source_id=source_id,
        assignee=assignee,
    )
    db.add(todo)
    await db.flush()
    return todo


async def update_todo(db: AsyncSession, todo_id: str, **updates) -> Todo:
    todo = await get_todo(db, todo_id)
    apply_model_updates(todo, updates)

    if "status" in updates:
        if updates["status"] == "completed" and not todo.completed_at:
            todo.completed_at = datetime.now(timezone.utc)
        elif updates["status"] != "completed":
            todo.completed_at = None

    await db.flush()
    return todo


async def delete_todo(db: AsyncSession, todo_id: str) -> None:
    todo = await get_todo(db, todo_id)
    await db.delete(todo)
    await db.flush()
