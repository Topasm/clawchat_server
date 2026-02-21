from fastapi import APIRouter, Depends

from auth.dependencies import get_current_user
from schemas.common import PaginatedResponse

router = APIRouter()


@router.get("", response_model=PaginatedResponse)
async def search(_user: str = Depends(get_current_user)):
    return PaginatedResponse(items=[], total=0, page=1, limit=20)
