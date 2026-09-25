"""Unified error handling for the NetWM API.

Every error returned by this API has the single shape:
    {"error": {"code": "...", "message": "..."}}
FastAPI's default {"detail": ...} is never leaked.
"""

from __future__ import annotations

import logging
from typing import Any
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("netwm.backend")

ERROR_STATUS_MAP: dict[str, int] = {
    "bad_file": 400,
    "unsupported_format": 415,
    "too_large": 413,
    "no_model": 503,
    "job_not_found": 404,
    "internal": 500,
}


class APIError(Exception):
    """Domain exception with an explicit error code and human-readable message."""

    def __init__(self, code: str, message: str, status_code: int | None = None) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code or ERROR_STATUS_MAP.get(code, 500)
        super().__init__(message)


def error_payload(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message}}


def register_error_handlers(app: FastAPI) -> None:
    """Register custom exception handlers on the FastAPI app."""

    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(exc.code, exc.message),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        first_err = exc.errors()[0] if exc.errors() else {"msg": "Invalid request parameter"}
        msg = first_err.get("msg", "Invalid request parameters")
        return JSONResponse(
            status_code=400,
            content=error_payload("bad_file", f"Validation error: {msg}"),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code_map = {
            400: "bad_file",
            404: "job_not_found",
            413: "too_large",
            415: "unsupported_format",
            503: "no_model",
        }
        code = code_map.get(exc.status_code, "internal")
        msg = str(exc.detail) if exc.detail else "An HTTP error occurred"
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(code, msg),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled server error: %s", exc)
        return JSONResponse(
            status_code=500,
            content=error_payload(
                "internal",
                "An unexpected internal error occurred while processing the request.",
            ),
        )
