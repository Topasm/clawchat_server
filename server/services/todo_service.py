"""Async service layer for todo CRUD operations."""

import json
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions import NotFoundError
from models.todo import Todo
from utils import make_id


async def get_todos(
    db: AsyncSession,
    *,
    status_filter: str | None = None,
    priority: str | None = None,
    due_before: datetime | None = None,
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

    count_q = select(func.count(Todo.id)).where(*conditions)
    total = (await db.execute(count_q)).scalar() or 0

    q = (
        select(Todo)
        .where(*conditions)
        .order_by(Todo.created_at.desc())
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
) -> Todo:
    todo = Todo(
        id=make_id("todo_"),
        title=title,
        description=description,
        priority=priority,
        due_date=due_date,
        tags=json.dumps(tags) if tags else None,
    )
    db.add(todo)
    await db.flush()
    return todo


async def update_todo(db: AsyncSession, todo_id: str, **updates) -> Todo:
    todo = await get_todo(db, todo_id)
    for key, value in updates.items():
        if key == "tags":
            setattr(todo, key, json.dumps(value) if value else None)
        else:
            setattr(todo, key, value)

    if "status" in updates:
        if updates["status"] == "completed" and not todo.completed_at:
            todo.completed_at = datetime.now(timezone.utc)
        elif updates["status"] != "completed":
            todo.completed_at = None

    todo.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return todo


async def delete_todo(db: AsyncSession, todo_id: str) -> None:
    todo = await get_todo(db, todo_id)
    await db.delete(todo)
    await db.flush()
