import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, JSONResponse, Response

from guitarcv_restapi.api.dependencies import (
    get_conversion_service,
    get_local_storage,
)
from guitarcv_restapi.api.v1.schemas.conversions import (
    ConversionFailure,
    ConversionStatusResponse,
    FailedConversionResponse,
)
from guitarcv_restapi.core.exceptions import ApiException
from guitarcv_restapi.models.conversion import ConversionStatus
from guitarcv_restapi.services.conversion_service import ConversionService
from guitarcv_restapi.storage.local_storage import LocalStorage


logger = logging.getLogger(__name__)


router = APIRouter()


@router.get(
    "/conversions/{conversion_id}",
    response_model=ConversionStatusResponse,
    status_code=202,
)
def get_conversion_status(
    conversion_id: str,
    conversion_service: Annotated[
        ConversionService,
        Depends(get_conversion_service),
    ],
) -> ConversionStatusResponse:
    conversion = conversion_service.get_conversion(conversion_id)

    if conversion is None:
        raise ApiException(
            status_code=400,
            code="CONVERSION_NOT_FOUND",
            message="The specified conversion does not exist.",
        )

    return ConversionStatusResponse(
        status=conversion.status,
    )


@router.get(
    "/conversions/{conversion_id}/result",
    response_model=None,
)
def get_conversion_result(
    conversion_id: str,
    conversion_service: Annotated[
        ConversionService,
        Depends(get_conversion_service),
    ],
    storage: Annotated[
        LocalStorage,
        Depends(get_local_storage),
    ],
) -> Response:
    conversion = conversion_service.get_conversion(conversion_id)

    if conversion is None:
        raise ApiException(
            status_code=404,
            code="CONVERSION_NOT_FOUND",
            message="The specified conversion does not exist.",
        )

    if conversion.status == ConversionStatus.PROCESSING:
        raise ApiException(
            status_code=409,
            code="CONVERSION_NOT_READY",
            message="The conversion has not finished yet.",
        )

    if conversion.status == ConversionStatus.FAILED:
        response = FailedConversionResponse(
            conversion_id=conversion.conversion_id,
            status="failed",
            error=ConversionFailure(
                message=conversion.error_message
                or "The conversion could not be completed.",
            ),
        )

        return JSONResponse(
            content=response.model_dump(by_alias=True),
            status_code=200,
        )

    now = datetime.now(timezone.utc)
    result_expired = (
        conversion.result_expires_at is not None
        and conversion.result_expires_at <= now
    )

    if result_expired:
        raise ApiException(
            status_code=410,
            code="RESULT_EXPIRED",
            message="The MIDI result has expired and is no longer available.",
        )

    if conversion.result_path is None:
        logger.error(
            "Conversion %s is marked ready but has no result path.",
            conversion_id,
        )
        raise ApiException(
            status_code=500,
            code="RESULT_FILE_MISSING",
            message="The conversion result is temporarily unavailable.",
        )

    result_path = conversion.result_path
    expected_result_path = storage.result_path_for(conversion_id)

    # Dont let a stale/malformed database path cause FileResponse to serve
    # an arbitrary file outside the configured results directory
    if result_path.resolve() != expected_result_path.resolve():
        logger.error(
            "Conversion %s references a result outside its canonical storage path",
            conversion_id,
        )
        raise ApiException(
            status_code=500,
            code="RESULT_FILE_PATH_INVALID",
            message="The conversion result is temporarily unavailable.",
        )

    if not storage.file_exists(expected_result_path):
        logger.error(
            "Result file for conversion %s does not exist at %s.",
            conversion_id,
            expected_result_path,
        )
        raise ApiException(
            status_code=500,
            code="RESULT_FILE_MISSING",
            message="The conversion result is temporarily unavailable.",
        )

    return FileResponse(
        path=expected_result_path,
        media_type="audio/midi",
        filename="output.mid",
    )
