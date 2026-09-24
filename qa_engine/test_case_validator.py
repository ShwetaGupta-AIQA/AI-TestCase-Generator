"""Deterministic QA checks after structural validation and ID assignment."""


def validate_test_case(test_case, expected_requirement_id, expected_scenario_id):
    errors = []
    warnings = []
    if not test_case.title.strip():
        errors.append("Test case title is missing.")
    if not test_case.steps:
        errors.append("Test steps are missing.")
    elif any(not step.strip() for step in test_case.steps):
        errors.append("Test steps contain an empty step.")
    if not test_case.expected_result.strip():
        errors.append("Expected result is missing.")
    if test_case.requirement_id != expected_requirement_id:
        errors.append("Incorrect requirement ID.")
    if test_case.scenario_id != expected_scenario_id:
        errors.append("Incorrect scenario ID.")
    if not test_case.test_data:
        warnings.append("No test data was generated.")
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def find_duplicate_titles(test_cases):
    seen = set()
    duplicates = []
    for case in test_cases:
        title = case.title.strip().lower()
        if not title:
            continue
        if title in seen:
            duplicates.append(case.test_case_id)
        seen.add(title)
    return duplicates
