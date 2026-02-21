from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from database import get_db
from exceptions import ValidationError
from schemas.common import PaginatedResponse
from schemas.search import SearchHit
from services import search_service

router = APIRouter()


@router.get("", response_model=PaginatedResponse[SearchHit])
async def search(
    q: str = Query("", description="Search query"),
    types: str | None = Query(None, description="Comma-separated types: messages,todos,events,memos"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    if not q.strip():
        raise ValidationError("Query parameter 'q' is required")

    type_list = [t.strip() for t in types.split(",") if t.strip()] if types else None

    hits, total = await search_service.search(db, q.strip(), type_list, page, limit)

    return PaginatedResponse(items=hits, total=total, page=page, limit=limit)
