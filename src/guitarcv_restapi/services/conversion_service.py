from guitarcv_restapi.models.conversion import Conversion
from guitarcv_restapi.repositories.conversion_repository import (
    ConversionRepository,
)


class ConversionService:
    def __init__(
        self,
        repository: ConversionRepository,
    ) -> None:
        self.repository = repository

    def get_conversion(
        self,
        conversion_id: str,
    ) -> Conversion | None:
        return self.repository.get_by_id(conversion_id)
