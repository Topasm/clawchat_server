from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from database import get_db
from exceptions import NotFoundError
from models.memo import Memo
from schemas.common import PaginatedResponse
from schemas.memo import MemoCreate, MemoResponse, MemoUpdate
from utils import apply_model_updates, deserialize_tags, make_id, serialize_tags

router = APIRouter()


@router.get("", response_model=PaginatedResponse[MemoResponse])
async def list_memos(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    offset = (page - 1) * limit

    count_q = select(func.count(Memo.id))
    total = (await db.execute(count_q)).scalar() or 0

    q = (
        select(Memo)
        .order_by(Memo.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await db.execute(q)).scalars().all()

    items = []
    for row in rows:
        resp = MemoResponse.model_validate(row)
        if row.tags:
            resp.tags = deserialize_tags(row.tags)
        items.append(resp)

    return PaginatedResponse(items=items, total=total, page=page, limit=limit)


@router.post("", response_model=MemoResponse, status_code=201)
async def create_memo(
    body: MemoCreate,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    title = body.title if body.title else body.content[:50].strip()
    memo = Memo(
        id=make_id("memo_"),
        title=title,
        content=body.content,
        tags=serialize_tags(body.tags),
    )
    db.add(memo)
    await db.commit()
    await db.refresh(memo)

    resp = MemoResponse.model_validate(memo)
    if memo.tags:
        resp.tags = deserialize_tags(memo.tags)
    return resp


@router.get("/{memo_id}", response_model=MemoResponse)
async def get_memo(
    memo_id: str,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    memo = await db.get(Memo, memo_id)
    if not memo:
        raise NotFoundError("Memo not found")
    resp = MemoResponse.model_validate(memo)
    if memo.tags:
        resp.tags = deserialize_tags(memo.tags)
    return resp


@router.patch("/{memo_id}", response_model=MemoResponse)
async def update_memo(
    memo_id: str,
    body: MemoUpdate,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    memo = await db.get(Memo, memo_id)
    if not memo:
        raise NotFoundError("Memo not found")

    data = body.model_dump(exclude_unset=True)
    apply_model_updates(memo, data)
    await db.commit()
    await db.refresh(memo)

    resp = MemoResponse.model_validate(memo)
    if memo.tags:
        resp.tags = deserialize_tags(memo.tags)
    return resp


@router.delete("/{memo_id}", status_code=204)
async def delete_memo(
    memo_id: str,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    memo = await db.get(Memo, memo_id)
    if not memo:
        raise NotFoundError("Memo not found")
    await db.delete(memo)
    await db.commit()
