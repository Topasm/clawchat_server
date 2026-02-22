"""REST endpoints for agent tasks."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from database import get_db
from exceptions import NotFoundError
from models.agent_task import AgentTask
from schemas.common import PaginatedResponse
from schemas.task import AgentTaskResponse
from services import agent_task_service

router = APIRouter()


@router.get("", response_model=PaginatedResponse[AgentTaskResponse])
async def list_tasks(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    conditions = []
    if status:
        conditions.append(AgentTask.status == status)
    # Only show top-level tasks (not sub-tasks)
    conditions.append(AgentTask.parent_task_id == None)  # noqa: E711

    count_q = select(func.count(AgentTask.id)).where(*conditions)
    total = (await db.execute(count_q)).scalar() or 0

    q = (
        select(AgentTask)
        .where(*conditions)
        .order_by(AgentTask.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    rows = (await db.execute(q)).scalars().all()

    items = [AgentTaskResponse.model_validate(row) for row in rows]
    return PaginatedResponse(items=items, total=total, page=page, limit=limit)


@router.get("/{task_id}", response_model=AgentTaskResponse)
async def get_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    task = await db.get(AgentTask, task_id)
    if not task:
        raise NotFoundError("Task not found")

    resp = AgentTaskResponse.model_validate(task)

    # Include sub-tasks if this is a coordinator
    if task.agent_type == "coordinator":
        subs = await agent_task_service.get_sub_tasks(db, task_id)
        resp.sub_tasks = [AgentTaskResponse.model_validate(s) for s in subs]

    return resp


@router.post("/{task_id}/cancel", status_code=200)
async def cancel_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    task = await db.get(AgentTask, task_id)
    if not task:
        raise NotFoundError("Task not found")

    if task.status in ("queued", "running"):
        task.status = "failed"
        task.error = "Cancelled by user"
        await db.commit()
        return {"status": "cancelled", "task_id": task_id}

    return {"status": task.status, "task_id": task_id, "message": "Task already finished"}
