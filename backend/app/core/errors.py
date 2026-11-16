"""Domain errors, mapped to RFC 7807 problem responses in a single handler."""

from fastapi import Request
from fastapi.responses import JSONResponse


class DomainError(Exception):
    status_code = 409

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class NotFoundError(DomainError):
    status_code = 404


async def domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    return JSONResponse(
        status_code=exc.status_code,
        media_type="application/problem+json",
        content={
            "type": f"https://wallbit.local/problems/{exc.code}",
            "title": exc.code,
            "status": exc.status_code,
            "detail": exc.detail,
            "code": exc.code,
        },
    )
