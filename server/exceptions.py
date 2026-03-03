from typing import Optional
from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 500, details: Optional[dict] = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


class UnauthorizedError(AppError):
    def __init__(self, message: str = "Missing or invalid authentication token"):
        super().__init__(code="UNAUTHORIZED", message=message, status_code=401)


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(code="NOT_FOUND", message=message, status_code=404)


class AIUnavailableError(AppError):
    def __init__(self, message: str = "AI provider is unreachable"):
        super().__init__(code="AI_UNAVAILABLE", message=message, status_code=503)


class ValidationError(AppError):
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(code="VALIDATION_ERROR", message=message, status_code=400, details=details)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    body: dict = {"code": exc.code, "message": exc.message}
    if exc.details:
        body["details"] = exc.details
    return JSONResponse(status_code=exc.status_code, content={"error": body})
