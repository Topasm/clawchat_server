from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from config import settings
from exceptions import UnauthorizedError

ALGORITHM = "HS256"


def create_access_token(subject: str = "user") -> tuple[str, int]:
    expires_delta = timedelta(hours=settings.jwt_expiry_hours)
    expires_in = int(expires_delta.total_seconds())
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {"sub": subject, "exp": expire, "type": "access"}
    token = jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)
    return token, expires_in


def create_refresh_token(subject: str = "user") -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=30)
    payload = {"sub": subject, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str, expected_type: str = "access") -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except JWTError:
        raise UnauthorizedError("Invalid or expired token")
    if payload.get("type") != expected_type:
        raise UnauthorizedError(f"Expected {expected_type} token")
    return payload


def verify_pin(pin: str) -> bool:
    return pin == settings.pin
