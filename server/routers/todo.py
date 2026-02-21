from fastapi import APIRouter, Depends

from auth.dependencies import get_current_user
from schemas.common import PaginatedResponse
from schemas.todo import TodoResponse

router = APIRouter()


@router.get("", response_model=PaginatedResponse[TodoResponse])
async def list_todos(_user: str = Depends(get_current_user)):
    return PaginatedResponse(items=[], total=0, page=1, limit=20)


@router.post("", status_code=501)
async def create_todo(_user: str = Depends(get_current_user)):
    return {"error": {"code": "NOT_IMPLEMENTED", "message": "Todo module coming soon"}}
