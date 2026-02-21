import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth.dependencies import get_current_user

router = APIRouter(tags=["notifications"])

logger = logging.getLogger(__name__)

# Simple in-memory token store (single-user app)
_push_tokens: list[str] = []


class RegisterTokenRequest(BaseModel):
    token: str
    device_id: str | None = None


@router.post("/register-token")
async def register_push_token(
    data: RegisterTokenRequest,
    _user: str = Depends(get_current_user),
):
    if data.token not in _push_tokens:
        _push_tokens.append(data.token)
        logger.info("Registered push token: %s", data.token[:20] + "...")
    return {"status": "registered"}
