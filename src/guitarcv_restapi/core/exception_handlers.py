import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from guitarcv_restapi.core.exceptions import ApiException


logger = logging.getLogger(__name__)


async def handle_api_exception(
    request: Request,
    exc: ApiException,
) -> JSONResponse:
    ... # TODO


async def handle_http_exception(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    ... # TODO


async def handle_validation_exception(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    ... # TODO


async def handle_unexpected_exception(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    ... # TODO


def register_exception_handlers(
    app: FastAPI,
) -> None:
    app.add_exception_handler(
        ApiException,
        handle_api_exception,
    )

    app.add_exception_handler(
        StarletteHTTPException,
        handle_http_exception,
    )

    app.add_exception_handler(
        RequestValidationError,
        handle_validation_exception,
    )

    app.add_exception_handler(
        Exception,
        handle_unexpected_exception,
    )