import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, JSONResponse, Response

from guitarcv_restapi.api.dependencies import get_conversion_service
from guitarcv_restapi.api.v1.schemas.conversions import (
    ConversionStatusResponse,
    FailedConversionResponse,
    ConversionFailure,
)
from guitarcv_restapi.core.exceptions import ApiException
from guitarcv_restapi.models.conversion import ConversionStatus
from guitarcv_restapi.services.conversion_service import ConversionService


router = APIRouter()

logger = logging.getLogger(__name__)


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

    result_path = Path(conversion.result_path)

    if not result_path.is_file():
        logger.error(
            "Result file for conversion %s does not exist.",
            conversion_id,
        )

        raise ApiException(
            status_code=500,
            code="RESULT_FILE_MISSING",
            message="The conversion result is temporarily unavailable.",
        )

    return FileResponse(
        path=result_path,
        media_type="audio/midi",
        filename="output.mid",
    )
