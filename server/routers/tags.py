from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from database import get_db
from models.event import Event
from models.memo import Memo
from models.todo import Todo
from utils import deserialize_tags

router = APIRouter(tags=["tags"])


@router.get("")
async def get_tags(
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    unique_tags: set[str] = set()

    # Collect tags from todos
    todo_q = select(Todo.tags).where(Todo.tags != None)  # noqa: E711
    todo_rows = (await db.execute(todo_q)).scalars().all()
    for raw in todo_rows:
        unique_tags.update(deserialize_tags(raw))

    # Collect tags from events
    event_q = select(Event.tags).where(Event.tags != None)  # noqa: E711
    event_rows = (await db.execute(event_q)).scalars().all()
    for raw in event_rows:
        unique_tags.update(deserialize_tags(raw))

    # Collect tags from memos
    memo_q = select(Memo.tags).where(Memo.tags != None)  # noqa: E711
    memo_rows = (await db.execute(memo_q)).scalars().all()
    for raw in memo_rows:
        unique_tags.update(deserialize_tags(raw))

    return {"tags": sorted(unique_tags)}
