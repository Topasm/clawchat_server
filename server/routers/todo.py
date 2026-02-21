import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from database import get_db
from exceptions import NotFoundError
from models.todo import Todo
from schemas.common import PaginatedResponse
from schemas.todo import TodoCreate, TodoResponse, TodoUpdate
from utils import make_id

router = APIRouter()


@router.get("", response_model=PaginatedResponse[TodoResponse])
async def list_todos(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: str | None = None,
    priority: str | None = None,
    due_before: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    offset = (page - 1) * limit
    conditions = []
    if status:
        conditions.append(Todo.status == status)
    if priority:
        conditions.append(Todo.priority == priority)
    if due_before:
        conditions.append(Todo.due_date <= due_before)

    count_q = select(func.count(Todo.id)).where(*conditions)
    total = (await db.execute(count_q)).scalar() or 0

    q = (
        select(Todo)
        .where(*conditions)
        .order_by(Todo.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await db.execute(q)).scalars().all()

    items = []
    for row in rows:
        resp = TodoResponse.model_validate(row)
        if row.tags:
            resp.tags = json.loads(row.tags)
        items.append(resp)

    return PaginatedResponse(items=items, total=total, page=page, limit=limit)


@router.post("", response_model=TodoResponse, status_code=201)
async def create_todo(
    body: TodoCreate,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    todo = Todo(
        id=make_id("todo_"),
        title=body.title,
        description=body.description,
        priority=body.priority,
        due_date=body.due_date,
        tags=json.dumps(body.tags) if body.tags else None,
    )
    db.add(todo)
    await db.commit()
    await db.refresh(todo)

    resp = TodoResponse.model_validate(todo)
    if todo.tags:
        resp.tags = json.loads(todo.tags)
    return resp


@router.get("/{todo_id}", response_model=TodoResponse)
async def get_todo(
    todo_id: str,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    todo = await db.get(Todo, todo_id)
    if not todo:
        raise NotFoundError("Todo not found")
    resp = TodoResponse.model_validate(todo)
    if todo.tags:
        resp.tags = json.loads(todo.tags)
    return resp


@router.patch("/{todo_id}", response_model=TodoResponse)
async def update_todo(
    todo_id: str,
    body: TodoUpdate,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    todo = await db.get(Todo, todo_id)
    if not todo:
        raise NotFoundError("Todo not found")

    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        if key == "tags":
            setattr(todo, key, json.dumps(value) if value else None)
        else:
            setattr(todo, key, value)

    # Auto-set completed_at when status changes to completed
    if "status" in data:
        if data["status"] == "completed" and not todo.completed_at:
            todo.completed_at = datetime.now(timezone.utc)
        elif data["status"] != "completed":
            todo.completed_at = None

    todo.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(todo)

    resp = TodoResponse.model_validate(todo)
    if todo.tags:
        resp.tags = json.loads(todo.tags)
    return resp


@router.delete("/{todo_id}", status_code=204)
async def delete_todo(
    todo_id: str,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    todo = await db.get(Todo, todo_id)
    if not todo:
        raise NotFoundError("Todo not found")
    await db.delete(todo)
    await db.commit()
