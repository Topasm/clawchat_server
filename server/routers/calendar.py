from fastapi import APIRouter, Depends

from auth.dependencies import get_current_user
from schemas.calendar import EventResponse
from schemas.common import PaginatedResponse

router = APIRouter()


@router.get("", response_model=PaginatedResponse[EventResponse])
async def list_events(_user: str = Depends(get_current_user)):
    return PaginatedResponse(items=[], total=0, page=1, limit=50)


@router.post("", status_code=501)
async def create_event(_user: str = Depends(get_current_user)):
    return {"error": {"code": "NOT_IMPLEMENTED", "message": "Calendar module coming soon"}}
