from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from database import get_db
from exceptions import NotFoundError
from models.todo import Todo
from schemas.bulk import BulkTodoResponse, BulkTodoUpdate
from schemas.common import PaginatedResponse
from schemas.todo import TodoCreate, TodoResponse, TodoUpdate
from utils import apply_model_updates, deserialize_tags, make_id, serialize_tags

router = APIRouter()

_ORDER_COLUMNS = {
    "created_at": Todo.created_at,
    "updated_at": Todo.updated_at,
    "sort_order": Todo.sort_order,
    "priority": Todo.priority,
}


@router.get("", response_model=PaginatedResponse[TodoResponse])
async def list_todos(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: str | None = None,
    priority: str | None = None,
    due_before: datetime | None = None,
    parent_id: str | None = None,
    root_only: bool = False,
    order_by: str = "created_at",
    order_dir: str = "desc",
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
    if parent_id:
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
        .offset(offset)
        .limit(limit)
    )
    rows = (await db.execute(q)).scalars().all()

    items = []
    for row in rows:
        resp = TodoResponse.model_validate(row)
        if row.tags:
            resp.tags = deserialize_tags(row.tags)
        items.append(resp)

    return PaginatedResponse(items=items, total=total, page=page, limit=limit)


@router.patch("/bulk", response_model=BulkTodoResponse)
async def bulk_update_todos(
    body: BulkTodoUpdate,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    updated = 0
    deleted = 0
    errors: list[str] = []
    for todo_id in body.ids:
        todo = await db.get(Todo, todo_id)
        if not todo:
            errors.append(f"Todo {todo_id} not found")
            continue
        if body.delete:
            await db.delete(todo)
            deleted += 1
        else:
            if body.status is not None:
                todo.status = body.status
                if body.status == "completed" and not todo.completed_at:
                    todo.completed_at = datetime.now(timezone.utc)
                elif body.status != "completed":
                    todo.completed_at = None
            if body.priority is not None:
                todo.priority = body.priority
            if body.tags is not None:
                todo.tags = serialize_tags(body.tags)
            todo.updated_at = datetime.now(timezone.utc)
            updated += 1
    await db.commit()
    return BulkTodoResponse(updated=updated, deleted=deleted, errors=errors)


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
        tags=serialize_tags(body.tags),
        parent_id=body.parent_id,
        sort_order=body.sort_order or 0,
        source=body.source,
        source_id=body.source_id,
        assignee=body.assignee,
    )
    db.add(todo)
    await db.commit()
    await db.refresh(todo)

    resp = TodoResponse.model_validate(todo)
    if todo.tags:
        resp.tags = deserialize_tags(todo.tags)
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
        resp.tags = deserialize_tags(todo.tags)
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
    apply_model_updates(todo, data)

    # Auto-set completed_at when status changes to completed
    if "status" in data:
        if data["status"] == "completed" and not todo.completed_at:
            todo.completed_at = datetime.now(timezone.utc)
        elif data["status"] != "completed":
            todo.completed_at = None
    await db.commit()
    await db.refresh(todo)

    resp = TodoResponse.model_validate(todo)
    if todo.tags:
        resp.tags = deserialize_tags(todo.tags)
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
