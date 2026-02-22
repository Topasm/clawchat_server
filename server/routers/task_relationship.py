from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from database import get_db
from exceptions import NotFoundError
from models.task_relationship import TaskRelationship
from models.todo import Todo
from schemas.task_relationship import (
    VALID_RELATIONSHIP_TYPES,
    TaskRelationshipCreate,
    TaskRelationshipResponse,
)
from utils import make_id

router = APIRouter()


@router.get("", response_model=list[TaskRelationshipResponse])
async def list_relationships(
    todo_id: str = Query(..., description="Return relationships where this todo is source or target"),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    q = select(TaskRelationship).where(
        or_(
            TaskRelationship.source_todo_id == todo_id,
            TaskRelationship.target_todo_id == todo_id,
        )
    )
    rows = (await db.execute(q)).scalars().all()
    return [TaskRelationshipResponse.model_validate(r) for r in rows]


@router.post("", response_model=TaskRelationshipResponse, status_code=201)
async def create_relationship(
    body: TaskRelationshipCreate,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    if body.relationship_type not in VALID_RELATIONSHIP_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid relationship_type. Must be one of: {', '.join(sorted(VALID_RELATIONSHIP_TYPES))}",
        )
    if body.source_todo_id == body.target_todo_id:
        raise HTTPException(status_code=422, detail="Cannot create a relationship to self")

    # Verify both todos exist
    source = await db.get(Todo, body.source_todo_id)
    if not source:
        raise NotFoundError(f"Source todo {body.source_todo_id} not found")
    target = await db.get(Todo, body.target_todo_id)
    if not target:
        raise NotFoundError(f"Target todo {body.target_todo_id} not found")

    rel = TaskRelationship(
        id=make_id("trel_"),
        source_todo_id=body.source_todo_id,
        target_todo_id=body.target_todo_id,
        relationship_type=body.relationship_type,
    )
    db.add(rel)
    await db.commit()
    await db.refresh(rel)
    return TaskRelationshipResponse.model_validate(rel)


@router.delete("/{relationship_id}", status_code=204)
async def delete_relationship(
    relationship_id: str,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    rel = await db.get(TaskRelationship, relationship_id)
    if not rel:
        raise NotFoundError("Relationship not found")
    await db.delete(rel)
    await db.commit()
