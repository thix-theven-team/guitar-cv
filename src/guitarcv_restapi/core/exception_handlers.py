import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from guitarcv_restapi.core.exceptions import ApiException


logger = logging.getLogger(__name__)


def _error_response(
    status_code: int,
    code: str,
    message: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content={
            "status": "error",
            "error": {
                "code": code,
                "message": message,
            },
        },
    )


async def handle_api_exception(
    request: Request,
    exc: ApiException,
) -> JSONResponse:
    if exc.status_code >= 500:
        logger.error(
            "Application error %s while handling %s %s: %s",
            exc.code,
            request.method,
            request.url.path,
            exc.message,
        )

    return _error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
    )


async def handle_http_exception(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    known_errors = {
        400: ("BAD_REQUEST", "The request could not be processed."),
        401: ("UNAUTHORIZED", "Authentication is required."),
        403: ("FORBIDDEN", "The requested operation is not permitted."),
        404: ("NOT_FOUND", "The requested resource was not found."),
        405: ("METHOD_NOT_ALLOWED", "The HTTP method is not allowed."),
        409: ("CONFLICT", "The request conflicts with the current resource state."),
        410: ("GONE", "The requested resource is no longer available."),
        413: ("CONTENT_TOO_LARGE", "The uploaded content is too large."),
        415: ("UNSUPPORTED_MEDIA_TYPE", "The supplied media type is not supported."),
        429: ("TOO_MANY_REQUESTS", "Too many requests."),
    }

    code, message = known_errors.get(
        exc.status_code,
        ("HTTP_ERROR", "The request could not be completed."),
    )

    if exc.status_code >= 500:
        logger.error(
            "HTTP %d while handling %s %s",
            exc.status_code,
            request.method,
            request.url.path,
        )

    return _error_response(
        status_code=exc.status_code,
        code=code,
        message=message,
        headers=exc.headers,
    )


async def handle_validation_exception(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    logger.warning(
        "Request validation failed for %s %s",
        request.method,
        request.url.path,
    )
    return _error_response(
        status_code=400,
        code="INVALID_REQUEST",
        message="Request validation failed.",
    )


async def handle_unexpected_exception(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.exception(
        "Unhandled exception while handling %s %s",
        request.method,
        request.url.path,
    )
    return _error_response(
        status_code=500,
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected server error occurred.",
    )


def register_exception_handlers(
    app: FastAPI,
) -> None:
    app.add_exception_handler(ApiException, handle_api_exception)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(RequestValidationError, handle_validation_exception)
    app.add_exception_handler(Exception, handle_unexpected_exception)
