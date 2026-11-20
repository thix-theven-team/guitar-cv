from fastapi import APIRouter

from guitarcv_restapi.api.v1.endpoints import (
    submissions,
    conversions,
)


router = APIRouter()

router.include_router(
    submissions.router,
    tags=["Submissions"],
)

router.include_router(
    conversions.router,
    tags=["Conversions"],
)