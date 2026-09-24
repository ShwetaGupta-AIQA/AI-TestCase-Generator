from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# Test inputs can intentionally be empty or whitespace-only. Preserve them exactly.
TestDataValue = Annotated[str, StringConstraints(min_length=0, strip_whitespace=False)]

class TestCase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    test_case_id: str
    requirement_id: str
    scenario_id: str
    title: str
    test_type: Literal["Functional", "Negative", "Boundary"]
    priority: Literal["High", "Medium", "Low"]
    preconditions: list[str]
    steps: list[str]
    test_data: dict[str, TestDataValue]
    expected_result: str

class TestCaseResponse(BaseModel):
    test_cases: list[TestCase] = Field(min_length=1)
