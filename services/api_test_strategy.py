"""Select a review/export scope without changing the generated source plan."""
from collections import Counter
from models.api_testing import ApiTestPlan


STRATEGIES = {
    "Smoke": ["Functional", "Negative"],
    "Standard": ["Functional", "Negative", "Boundary/Validation", "Error Handling"],
    "Advanced": ["Functional", "Negative", "Boundary/Validation", "Error Handling", "Idempotency", "Observability"],
}


def select_test_scope(plan: ApiTestPlan, categories: list[str], excluded_ids: list[str] | None = None) -> ApiTestPlan:
    selected = plan.model_copy(deep=True)
    excluded = set(excluded_ids or [])
    selected.test_cases = [case for case in selected.test_cases
                           if case.test_type in categories and case.test_case_id not in excluded]
    selected.coverage_summary = dict(Counter(case.test_type for case in selected.test_cases))
    return selected


def review_test_cases(plan: ApiTestPlan, rows: list[dict]) -> ApiTestPlan:
    """Validate review edits atomically, retaining IDs and request definitions."""
    reviewed = plan.model_copy(deep=True)
    cases = {case.test_case_id: case for case in reviewed.test_cases}
    seen = set()
    for row in rows:
        case_id = row.get("test_case_id")
        if case_id not in cases or case_id in seen:
            raise ValueError("Review contains an unknown or duplicate test ID.")
        seen.add(case_id)
        status = str(row.get("expected_status", "")).strip()
        if status != "Needs confirmation" and not (len(status) == 3 and status.isascii() and status.isdigit() and 100 <= int(status) <= 599):
            raise ValueError(f"{case_id}: enter an HTTP status from 100 to 599, or Needs confirmation.")
        priority = row.get("priority")
        if priority not in {"High", "Medium", "Low"}:
            raise ValueError(f"{case_id}: select High, Medium or Low priority.")
        result = row.get("expected_result")
        if not isinstance(result, str) or not result.strip():
            raise ValueError(f"{case_id}: expected result cannot be empty.")
        case = cases[case_id]
        case.expected_status = status
        case.priority = priority
        case.expected_result = result.strip()
    return reviewed
