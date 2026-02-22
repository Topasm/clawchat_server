"""Async service layer for memo CRUD operations."""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions import NotFoundError
from models.memo import Memo
from utils import apply_model_updates, make_id, serialize_tags


async def get_memos(
    db: AsyncSession,
    *,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[Memo], int]:
    count_q = select(func.count(Memo.id))
    total = (await db.execute(count_q)).scalar() or 0

    q = (
        select(Memo)
        .order_by(Memo.updated_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    rows = (await db.execute(q)).scalars().all()
    return list(rows), total


async def get_memo(db: AsyncSession, memo_id: str) -> Memo:
    memo = await db.get(Memo, memo_id)
    if not memo:
        raise NotFoundError(f"Memo {memo_id} not found")
    return memo


async def create_memo(
    db: AsyncSession,
    *,
    title: str,
    content: str,
    tags: list[str] | None = None,
) -> Memo:
    memo = Memo(
        id=make_id("memo_"),
        title=title,
        content=content,
        tags=serialize_tags(tags),
    )
    db.add(memo)
    await db.flush()
    return memo


async def update_memo(db: AsyncSession, memo_id: str, **updates) -> Memo:
    memo = await get_memo(db, memo_id)
    apply_model_updates(memo, updates)
    await db.flush()
    return memo


async def delete_memo(db: AsyncSession, memo_id: str) -> None:
    memo = await get_memo(db, memo_id)
    await db.delete(memo)
    await db.flush()
