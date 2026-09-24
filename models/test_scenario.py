from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class TestScenario(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, str_min_length=1)
    scenario_id: str
    requirement_id: str
    title: str
    scenario_type: Literal["Functional", "Negative", "Boundary"]
    description: str

class TestScenarioResponse(BaseModel):
    scenarios: list[TestScenario] = Field(min_length=1)
