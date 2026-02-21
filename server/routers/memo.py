from fastapi import APIRouter, Depends

from auth.dependencies import get_current_user
from schemas.common import PaginatedResponse
from schemas.memo import MemoResponse

router = APIRouter()


@router.get("", response_model=PaginatedResponse[MemoResponse])
async def list_memos(_user: str = Depends(get_current_user)):
    return PaginatedResponse(items=[], total=0, page=1, limit=20)


@router.post("", status_code=501)
async def create_memo(_user: str = Depends(get_current_user)):
    return {"error": {"code": "NOT_IMPLEMENTED", "message": "Memo module coming soon"}}
