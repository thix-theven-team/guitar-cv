from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    UploadFile,
)

from guitarcv_restapi.api.dependencies import get_submission_service
from guitarcv_restapi.api.v1.schemas.submissions import SubmissionResponse
from guitarcv_restapi.core.exceptions import ApiException
from guitarcv_restapi.processing.tasks import process_conversion_task
from guitarcv_restapi.services.submission_service import SubmissionService



router = APIRouter()


@router.post(
    "/submit-video",
    response_model=SubmissionResponse,
    status_code=200,
)
def submit_video(
    background_tasks: BackgroundTasks,
    submission_service: Annotated[
        SubmissionService,
        Depends(get_submission_service),
    ],
    video: Annotated[UploadFile | None, File()] = None,
) -> SubmissionResponse:
    if video is None:
        raise ApiException(
            status_code=400,
            code="MISSING_VIDEO",
            message="The required video field is missing.",
        )

    conversion_id = submission_service.submit_video(
        file=video.file,
        content_type=video.content_type,
    )

    background_tasks.add_task(
        process_conversion_task,
        conversion_id,
    )

    return SubmissionResponse(
        conversion_id=conversion_id,
    )
