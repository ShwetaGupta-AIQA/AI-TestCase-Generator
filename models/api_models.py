from pydantic import BaseModel, ConfigDict, Field

from models.requirement import RequirementAnalysis
from models.test_scenario import TestScenario
from models.document_requirement import ExtractedRequirement
from models.api_testing import ApiEndpointChoice, ApiTestPlan


class RequirementRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    requirement: str = Field(min_length=5, description="Requirement or user story to analyze")


class RunRequest(RequirementRequest):
    idempotency_key: str = Field(min_length=1, max_length=128)


class ScenarioResponse(BaseModel):
    requirement_analysis: RequirementAnalysis
    scenarios: list[TestScenario]


class DocumentUploadResponse(BaseModel):
    filename: str
    requirements_found: int
    requirements: list[ExtractedRequirement]


class WorkspaceResponse(BaseModel):
    workspace_token: str


class ApiSpecParseResponse(BaseModel):
    title: str
    base_url: str
    endpoints: list[ApiEndpointChoice]


class ApiTestDesignResponse(BaseModel):
    plan: ApiTestPlan
