from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from guitarcv_restapi.models.conversion import ConversionStatus


class ConversionStatusResponse(BaseModel):
    status: ConversionStatus


class ConversionFailure(BaseModel):
    message: str


class FailedConversionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    conversion_id: str = Field(alias="conversion-id")
    status: Literal["failed"]
    error: ConversionFailure
