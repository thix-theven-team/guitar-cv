from guitarcv_restapi.models.conversion import Conversion
from guitarcv_restapi.repositories.conversion_repository import (
    ConversionRepository,
)


class ConversionService:
    def __init__(
        self,
        repository: ConversionRepository,
    ) -> None:
        ... # TODO

    def get_conversion(
        self,
        conversion_id: str,
    ) -> Conversion | None:
        ... # TODO