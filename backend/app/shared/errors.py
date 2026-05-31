"""Uniform error envelope.

Matches the contract in openapi-v1.yaml:
    {"error": {"code", "message", "details", "request_id"}}

Status code is passed explicitly (no request.state mutation). Validation
payloads are run through jsonable_encoder so they are always serializable, and a
catch-all handler keeps unexpected errors inside the envelope without leaking
internals.
"""
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
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


def _envelope(
    status_code: int,
    code: str,
    message: str,
    request: Request,
    details: dict | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "request_id": request.headers.get("x-request-id"),
            }
        },
    )


_HTTP_CODE = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return _envelope(exc.status_code, exc.code, exc.message, request, exc.details)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODE.get(exc.status_code, "http_error")
        return _envelope(exc.status_code, code, str(exc.detail), request)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _envelope(
            422,
            "validation_error",
            "Request validation failed.",
            request,
            {"errors": jsonable_encoder(exc.errors())},
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Catch-all: keep the uniform envelope, never leak internals.
        return _envelope(500, "internal_error", "An unexpected error occurred.", request)
