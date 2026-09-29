"""Field-level design traceability, not execution or completeness scoring."""
from models.api_testing import ApiTestPlan


def field_design_coverage(plan: ApiTestPlan) -> list[dict]:
    endpoint = plan.endpoint
    rows = []
    for field in endpoint.headers + endpoint.query_params + endpoint.path_params + endpoint.body_fields:
        key = f"{field.location}:{field.name}"
        cases = [case for case in plan.test_cases if case.covered_field == key]
        rows.append({"Field": key, "Required": field.required,
                     "Documented constraints": ", ".join(name for name in field.schema_definition
                         if name in {"minimum", "maximum", "minLength", "maxLength", "enum", "pattern", "format", "minItems", "maxItems", "exclusiveMinimum", "exclusiveMaximum"}),
                     "Selected test IDs": ", ".join(case.test_case_id for case in cases),
                     "Design status": "Has field-specific design" if cases else "No field-specific design",
                     "Needs status confirmation": sum(not case.expected_status.isdigit() for case in cases)})
    return rows
