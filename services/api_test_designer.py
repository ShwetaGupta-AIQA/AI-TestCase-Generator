from collections import Counter

from models.api_testing import ApiContract, ApiEndpoint, ApiParameter, ApiTestCase, ApiTestPlan


def _sample_value(param: ApiParameter, invalid: bool = False) -> str:
    if invalid:
        return ""
    if param.example is not None:
        return param.example
    name = param.name.lower()
    if "email" in name:
        return "qa.user@example.com"
    if "phone" in name or "mobile" in name:
        return "+919999999999"
    if "id" in name:
        return "12345"
    if param.data_type in {"integer", "number"}:
        return "1"
    if param.data_type == "boolean":
        return "true"
    return f"sample_{param.name}"


def _payload(endpoint: ApiEndpoint) -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, str]]:
    return (
        {p.name: _sample_value(p) for p in endpoint.headers},
        {p.name: _sample_value(p) for p in endpoint.query_params},
        {p.name: _sample_value(p) for p in endpoint.path_params},
        {p.name: _sample_value(p) for p in endpoint.body_fields},
    )


def _success_status(endpoint: ApiEndpoint) -> str:
    for response in endpoint.responses:
        if response.status_code.startswith("2"):
            return response.status_code
    return "200"


def _error_statuses(endpoint: ApiEndpoint) -> list[str]:
    statuses = [r.status_code for r in endpoint.responses if not r.status_code.startswith("2")]
    return statuses or ["400", "401", "404", "500"]


def _case(case_number: int, endpoint: ApiEndpoint, title: str, test_type: str, priority: str,
          objective: str, expected_status: str, expected_result: str,
          negative_reason: str = "", mutate=None) -> ApiTestCase:
    headers, query, path, body = _payload(endpoint)
    if mutate:
        mutate(headers, query, path, body)
    target = endpoint.path
    if path:
        for name, value in path.items():
            target = target.replace("{" + name + "}", value)
    return ApiTestCase(
        test_case_id=f"API-TC-{case_number:03d}",
        title=title,
        test_type=test_type,
        priority=priority,
        method=endpoint.method,
        path=target,
        objective=objective,
        preconditions=["Target environment is Mock, Local, Test or Staging.", "Authentication/test credentials are configured if the API requires them."],
        request_headers=headers,
        query_params=query,
        path_params=path,
        request_body=body,
        steps=[
            f"Send {endpoint.method} request to {target}.",
            "Capture status code, response headers, response body and response time.",
            "Validate the response against the contract and expected business rule.",
        ],
        expected_status=expected_status,
        expected_result=expected_result,
        negative_reason=negative_reason,
    )


def retrieve_api_context(contract: ApiContract, endpoint: ApiEndpoint) -> list[str]:
    context = [
        f"Selected endpoint: {endpoint.method} {endpoint.path}",
        f"Contract: {contract.title}",
    ]
    if endpoint.summary:
        context.append(f"Summary: {endpoint.summary}")
    if endpoint.description:
        context.append(f"Description: {endpoint.description[:600]}")
    if endpoint.responses:
        context.append("Responses: " + ", ".join(f"{r.status_code} {r.description}".strip() for r in endpoint.responses))
    related = [candidate for candidate in contract.endpoints
               if candidate.path != endpoint.path and endpoint.path.split("/")[1:2] == candidate.path.split("/")[1:2]]
    for candidate in related[:3]:
        context.append(f"Related operation: {candidate.method} {candidate.path} {candidate.summary}".strip())
    return context


def design_api_tests(contract: ApiContract, endpoint: ApiEndpoint) -> ApiTestPlan:
    tests: list[ApiTestCase] = []
    success = _success_status(endpoint)
    tests.append(_case(1, endpoint, "Valid request returns documented success response", "Functional", "High",
                       "Prove the API accepts a fully valid request.", success,
                       "Response status and schema match the documented success contract."))

    case_number = 2
    for param in [p for p in endpoint.headers + endpoint.query_params + endpoint.path_params + endpoint.body_fields if p.required]:
        def missing(headers, query, path, body, p=param):
            target = {"header": headers, "query": query, "path": path, "body": body}.get(p.location, body)
            target.pop(p.name, None)
        tests.append(_case(case_number, endpoint, f"Missing required {param.location} field {param.name}", "Negative", "High",
                           f"Verify validation when required {param.location} field {param.name} is absent.", "400",
                           "API rejects the request with a clear validation error.", f"{param.name} missing", missing))
        case_number += 1

    for param in endpoint.body_fields[:3] + endpoint.query_params[:2]:
        def invalid(headers, query, path, body, p=param):
            target = body if p.location == "body" else query
            target[p.name] = _sample_value(p, invalid=True)
        tests.append(_case(case_number, endpoint, f"Invalid value for {param.name}", "Boundary/Validation", "Medium",
                           f"Check type/format validation for {param.name}.", "400",
                           "API rejects invalid or boundary value and returns a useful error message.", "invalid value", invalid))
        case_number += 1

    for status in _error_statuses(endpoint):
        tests.append(_case(case_number, endpoint, f"Documented error handling for HTTP {status}", "Error Handling", "Medium",
                           f"Confirm the API behavior for documented HTTP {status}.", status,
                           "Response follows the documented error structure without leaking sensitive data."))
        case_number += 1

    if endpoint.method in {"POST", "PUT", "PATCH", "DELETE"}:
        tests.append(_case(case_number, endpoint, "Repeat request handles duplicate/idempotency behavior", "Idempotency", "High",
                           "Validate duplicate submission handling, idempotency key behavior or safe retry expectations.",
                           success, "Second request is handled according to contract: same resource, conflict, or documented retry response."))
        case_number += 1

    if any(p.name.lower() in {"request-id", "correlation-id", "x-request-id"} for p in endpoint.headers):
        tests.append(_case(case_number, endpoint, "Correlation identifier is preserved in response/logging", "Observability", "Medium",
                           "Verify request traceability through Request-Id/Correlation-Id.", success,
                           "Response headers/log reference preserve the request identifier for support triage."))

    counts = Counter(test.test_type for test in tests)
    return ApiTestPlan(contract_title=contract.title, base_url=contract.base_url, endpoint=endpoint,
                       coverage_summary=dict(counts), test_cases=tests,
                       retrieved_context=retrieve_api_context(contract, endpoint))
