from pydantic import BaseModel, ConfigDict


class ExtractedRequirement(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, str_min_length=1)
    source_id: str
    requirement_text: str


class RequirementExtractionResponse(BaseModel):
    requirements: list[ExtractedRequirement]
