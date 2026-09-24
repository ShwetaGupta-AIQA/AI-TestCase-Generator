from models.evaluation import EvaluationResult
from qa_engine.test_case_validator import find_duplicate_titles


def _complete(case):
    return bool(case.title.strip() and case.steps and
                all(step.strip() for step in case.steps) and case.expected_result.strip())


def _traceable(case, scenarios=None):
    if not case.requirement_id.strip() or not case.scenario_id.strip():
        return False
    if scenarios is None:
        return True
    matches = [s for s in scenarios if s.scenario_id == case.scenario_id]
    return len(matches) == 1 and matches[0].requirement_id == case.requirement_id


def _percentage(count, total):
    return count / total * 100 if total else 0.0


def evaluate_completeness(test_cases):
    return _percentage(sum(_complete(c) for c in test_cases), len(test_cases))


def evaluate_traceability(test_cases, scenarios=None):
    return _percentage(sum(_traceable(c, scenarios) for c in test_cases), len(test_cases))


def evaluate_duplicate_rate(test_cases):
    return _percentage(len(find_duplicate_titles(test_cases)), len(test_cases))


def evaluate_test_suite(test_cases, scenarios=None):
    total = len(test_cases)
    complete = sum(_complete(c) for c in test_cases)
    traceable = sum(_traceable(c, scenarios) for c in test_cases)
    duplicates = len(find_duplicate_titles(test_cases))
    issues = []
    if not total:
        issues.append("No test cases available for evaluation.")
    if complete < total:
        issues.append("Some test cases are incomplete.")
    if traceable < total:
        issues.append("Some test cases have missing or incorrect traceability.")
    if duplicates:
        issues.append("Duplicate test cases detected.")
    return EvaluationResult(
        total_test_cases=total, complete_test_cases=complete,
        traceable_test_cases=traceable, duplicate_test_cases=duplicates,
        completeness_score=round(_percentage(complete, total), 2),
        traceability_score=round(_percentage(traceable, total), 2),
        duplicate_rate=round(_percentage(duplicates, total), 2), issues=issues)


def evaluate_boundary_extraction(analysis, expected_minimum, expected_maximum, expected_unit):
    boundaries = analysis.boundary_constraints
    if expected_minimum is None and expected_maximum is None and expected_unit is None:
        return not boundaries
    # These golden examples each specify exactly one constraint; extras are errors.
    if len(boundaries) != 1:
        return False
    boundary = boundaries[0]
    normalize = lambda unit: unit.strip().lower() if unit else None
    return (boundary.minimum == expected_minimum and boundary.maximum == expected_maximum
            and normalize(boundary.unit) == normalize(expected_unit))
