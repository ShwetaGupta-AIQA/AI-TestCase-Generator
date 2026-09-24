"""Validated output from requirement analysis."""

from typing import List

from pydantic import BaseModel, Field, StrictInt, model_validator


class BoundaryConstraint(BaseModel):
    field: str = Field(min_length=1)
    minimum: StrictInt | None = None
    maximum: StrictInt | None = None
    unit: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_limits(self):
        if self.minimum is None and self.maximum is None:
            raise ValueError("A boundary constraint needs at least one explicit limit.")
        if self.minimum is not None and self.maximum is not None:
            if self.minimum > self.maximum:
                raise ValueError("Minimum must not exceed maximum.")
        return self


class RequirementAnalysis(BaseModel):
    requirement_id: str
    actor: str
    functionality: str
    business_rules: List[str]
    constraints: List[str]
    boundary_constraints: List[BoundaryConstraint]
    missing_information: List[str]
    assumptions: List[str]
    clarification_questions: List[str]
