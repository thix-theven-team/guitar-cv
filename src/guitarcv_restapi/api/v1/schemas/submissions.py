from pydantic import BaseModel, ConfigDict, Field


class SubmissionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    conversion_id: str = Field(alias="conversion-id")
