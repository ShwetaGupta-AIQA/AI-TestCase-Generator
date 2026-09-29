from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


class ApiParameter(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str
    location: Literal["path", "query", "header", "cookie", "body"] = "query"
    required: bool = False
    data_type: str = "string"
    description: str = ""
    example: Any = None
    schema_definition: dict[str, Any] = Field(default_factory=dict)


class ApiResponseSpec(BaseModel):
    status_code: str
    description: str = ""
    content: dict[str, Any] = Field(default_factory=dict)


class ApiEndpoint(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    method: HttpMethod
    path: str = Field(min_length=1)
    summary: str = ""
    description: str = ""
    operation_id: str = ""
    headers: list[ApiParameter] = Field(default_factory=list)
    query_params: list[ApiParameter] = Field(default_factory=list)
    path_params: list[ApiParameter] = Field(default_factory=list)
    body_fields: list[ApiParameter] = Field(default_factory=list)
    responses: list[ApiResponseSpec] = Field(default_factory=list)
    request_schema: dict[str, Any] = Field(default_factory=dict)
    security: list[dict[str, Any]] = Field(default_factory=list)
    source_reference: str = ""
    warnings: list[str] = Field(default_factory=list)


class ApiContract(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = "API Contract"
    base_url: str = ""
    endpoints: list[ApiEndpoint]
    source_type: Literal["manual", "openapi", "html"] = "manual"
    security_schemes: dict[str, Any] = Field(default_factory=dict)


class ApiManualRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: str = "Manual API"
    base_url: str = ""
    method: HttpMethod
    path: str = Field(min_length=1)
    summary: str = ""
    description: str = ""
    required_headers: list[str] = Field(default_factory=list)
    optional_headers: list[str] = Field(default_factory=list)
    required_query_params: list[str] = Field(default_factory=list)
    optional_query_params: list[str] = Field(default_factory=list)
    required_body_fields: list[str] = Field(default_factory=list)
    optional_body_fields: list[str] = Field(default_factory=list)
    success_status: str = "200"
    error_statuses: list[str] = Field(default_factory=list)


class ApiSpecRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    spec_text: str = ""
    url: str = ""
    endpoint_key: str | None = None
    reviewed_endpoint: ApiEndpoint | None = None


class ApiHtmlRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    html_text: str = ""
    url: str = ""
    endpoint_key: str | None = None
    reviewed_endpoint: ApiEndpoint | None = None


class ApiEndpointChoice(BaseModel):
    key: str
    label: str
    method: HttpMethod
    path: str
    summary: str = ""
    contract: ApiEndpoint | None = None


class ApiTestCase(BaseModel):
    test_case_id: str
    title: str
    test_type: str
    priority: Literal["High", "Medium", "Low"]
    method: HttpMethod
    path: str
    objective: str
    preconditions: list[str] = Field(default_factory=list)
    request_headers: dict[str, str] = Field(default_factory=dict)
    query_params: dict[str, str] = Field(default_factory=dict)
    path_params: dict[str, str] = Field(default_factory=dict)
    request_body: Any = Field(default_factory=dict)
    steps: list[str]
    expected_status: str
    expected_result: str
    negative_reason: str = ""
    covered_field: str = ""
    source: str = "Deterministic API QA Engine"


class ApiTestPlan(BaseModel):
    contract_title: str
    base_url: str
    endpoint: ApiEndpoint
    coverage_summary: dict[str, int]
    test_cases: list[ApiTestCase]
    retrieved_context: list[str] = Field(default_factory=list)
