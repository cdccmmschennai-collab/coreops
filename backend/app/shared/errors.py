"""Uniform error envelope.

Matches the contract in openapi-v1.yaml:
    {"error": {"code", "message", "details", "request_id"}}
"""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """Domain/application error mapped to the uniform envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


def _envelope(code: str, message: str, details: dict | None, request: Request) -> JSONResponse:
    request_id = request.headers.get("x-request-id")
    status = getattr(request.state, "_status_code", 400)
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "request_id": request_id,
            }
        },
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        request.state._status_code = exc.status_code
        return _envelope(exc.code, exc.message, exc.details, request)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        request.state._status_code = exc.status_code
        code = {
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            409: "conflict",
        }.get(exc.status_code, "http_error")
        return _envelope(code, str(exc.detail), None, request)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request.state._status_code = 422
        return _envelope(
            "validation_error",
            "Request validation failed.",
            {"errors": exc.errors()},
            request,
        )
