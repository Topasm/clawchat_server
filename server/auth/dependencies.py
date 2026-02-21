from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auth.jwt import decode_token
from exceptions import UnauthorizedError

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    if credentials is None:
        raise UnauthorizedError("Missing authorization header")
    payload = decode_token(credentials.credentials, expected_type="access")
    return payload["sub"]
