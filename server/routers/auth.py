from fastapi import APIRouter, Depends

from auth.dependencies import get_current_user
from auth.jwt import create_access_token, create_refresh_token, decode_token, verify_pin
from exceptions import UnauthorizedError
from schemas.auth import LoginRequest, RefreshRequest, TokenResponse

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    if not verify_pin(body.pin):
        raise UnauthorizedError("Invalid PIN")
    access_token, expires_in = create_access_token()
    refresh_token = create_refresh_token()
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest):
    payload = decode_token(body.refresh_token, expected_type="refresh")
    access_token, expires_in = create_access_token(subject=payload["sub"])
    refresh_token = create_refresh_token(subject=payload["sub"])
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )


@router.post("/logout")
async def logout(_user: str = Depends(get_current_user)):
    return {"message": "Logged out successfully"}
