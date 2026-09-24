from pydantic import BaseModel


class EvaluationResult(BaseModel):
    total_test_cases: int
    complete_test_cases: int
    traceable_test_cases: int
    duplicate_test_cases: int
    completeness_score: float
    traceability_score: float
    duplicate_rate: float
    issues: list[str]
