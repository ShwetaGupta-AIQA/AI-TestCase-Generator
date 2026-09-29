import json
import yaml
from typing import Any

from models.api_testing import (ApiContract, ApiEndpoint, ApiManualRequest,
                                ApiParameter, ApiResponseSpec)


HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def _schema_type(schema: dict[str, Any] | None) -> str:
    if not isinstance(schema, dict):
        return "string"
    if "$ref" in schema:
        return str(schema["$ref"]).split("/")[-1]
    if "type" in schema:
        return str(schema["type"])
    for keyword in ("oneOf", "anyOf", "allOf"):
        options = schema.get(keyword)
        if isinstance(options, list) and options:
            return _schema_type(options[0])
    return "object" if schema.get("properties") else "string"


def _resolve_ref(spec: dict[str, Any], value: Any) -> Any:
    if not isinstance(value, dict) or "$ref" not in value:
        return value
    ref = value["$ref"]
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return value
    current: Any = spec
    for part in ref[2:].split("/"):
        if not isinstance(current, dict):
            return value
        current = current.get(part.replace("~1", "/").replace("~0", "~"))
    if current is None:
        raise ValueError(f"Unresolved specification reference: {ref}")
    return current


def _expand_schema(spec, value, seen=()):
    if isinstance(value, list):
        return [_expand_schema(spec, item, seen) for item in value]
    if not isinstance(value, dict):
        return value
    if "$ref" in value:
        ref = value["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/"):
            raise ValueError("External references are not supported; upload a bundled specification.")
        if ref in seen:
            return value
        return _expand_schema(spec, _resolve_ref(spec, value), seen + (ref,))
    return {key: _expand_schema(spec, item, seen) for key, item in value.items()}


def _parameter_from_openapi(spec: dict[str, Any], item: dict[str, Any]) -> ApiParameter:
    resolved = _resolve_ref(spec, item)
    schema = resolved.get("schema") if isinstance(resolved, dict) else {}
    return ApiParameter(
        name=str(resolved.get("name", "unknown")),
        location=resolved.get("in", "query"),
        required=bool(resolved.get("required", False)),
        data_type=_schema_type(schema),
        description=str(resolved.get("description", "")),
        example=resolved.get("example", (schema or {}).get("example")),
        schema_definition=_expand_schema(spec, schema or {}),
    )


def _body_fields(spec: dict[str, Any], request_body: dict[str, Any] | None) -> list[ApiParameter]:
    if not isinstance(request_body, dict):
        return []
    resolved_body = _resolve_ref(spec, request_body)
    content = resolved_body.get("content", {}) if isinstance(resolved_body, dict) else {}
    media = content.get("application/json") or next(iter(content.values()), {})
    schema = _resolve_ref(spec, media.get("schema", {})) if isinstance(media, dict) else {}
    required = set(schema.get("required", [])) if isinstance(schema, dict) else set()
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
    fields = []
    if isinstance(properties, dict):
        for name, field_schema in properties.items():
            resolved = _resolve_ref(spec, field_schema)
            fields.append(ApiParameter(
                name=str(name),
                location="body",
                required=name in required,
                data_type=_schema_type(resolved),
                description=str(resolved.get("description", "")) if isinstance(resolved, dict) else "",
                example=resolved.get("example"),
                schema_definition=_expand_schema(spec, resolved),
            ))
    return fields


def parse_openapi_spec(spec_text: str) -> ApiContract:
    if len(spec_text.encode("utf-8")) > 2 * 1024 * 1024:
        raise ValueError("Specification exceeds the 2 MiB import limit.")
    try:
        spec = json.loads(spec_text)
    except json.JSONDecodeError:
        try:
            # Aliases can create recursive or exponentially expanded structures.
            if any(isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken))
                   for token in yaml.scan(spec_text)):
                raise ValueError("YAML anchors and aliases are unsupported. Expand them before importing.")
            spec = yaml.safe_load(spec_text)
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            location = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
            raise ValueError(f"Invalid JSON or YAML specification{location}.") from exc
    if not isinstance(spec, dict) or "paths" not in spec:
        raise ValueError("The uploaded specification does not look like an OpenAPI/Swagger document.")
    if not str(spec.get("openapi", "")).startswith(("3.0.", "3.1.")):
        raise ValueError("Supported versions: OpenAPI 3.0 and 3.1. Convert Swagger 2.0 before importing.")
    if not isinstance(spec["paths"], dict):
        raise ValueError("OpenAPI paths must be an object.")
    spec = _expand_schema(spec, spec)

    info = spec.get("info", {}) if isinstance(spec.get("info"), dict) else {}
    servers = spec.get("servers", [])
    base_url = ""
    if isinstance(servers, list) and servers and isinstance(servers[0], dict):
        base_url = str(servers[0].get("url", ""))
    elif isinstance(spec.get("host"), str):
        scheme = (spec.get("schemes") or ["https"])[0]
        base_path = spec.get("basePath", "")
        base_url = f"{scheme}://{spec['host']}{base_path}"

    endpoints: list[ApiEndpoint] = []
    for path, path_item in spec.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        shared_params = [_parameter_from_openapi(spec, item) for item in path_item.get("parameters", [])
                         if isinstance(item, dict)]
        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            params = shared_params + [_parameter_from_openapi(spec, item)
                                      for item in operation.get("parameters", []) if isinstance(item, dict)]
            responses = []
            for code, response in operation.get("responses", {}).items():
                resolved = _resolve_ref(spec, response)
                responses.append(ApiResponseSpec(status_code=str(code), content=resolved.get("content", {}),
                                                 description=str(resolved.get("description", "")) if isinstance(resolved, dict) else ""))
            request_content = operation.get("requestBody", {}).get("content", {})
            request_schema = request_content.get("application/json", {}).get("schema", {})
            endpoints.append(ApiEndpoint(
                method=method.upper(),
                path=str(path),
                summary=str(operation.get("summary", "")),
                description=str(operation.get("description", "")),
                operation_id=str(operation.get("operationId", "")),
                headers=[p for p in params if p.location == "header"],
                query_params=[p for p in params if p.location == "query"],
                path_params=[p for p in params if p.location == "path"],
                body_fields=_body_fields(spec, operation.get("requestBody")),
                responses=responses,
                request_schema=request_schema,
                security=operation.get("security", spec.get("security", [])),
                source_reference=f"#/paths/{str(path).replace('~', '~0').replace('/', '~1')}/{method}",
                warnings=["Review composed or recursive schemas before execution."] if any(
                    token in json.dumps(request_schema) for token in ('"$ref"', '"oneOf"', '"anyOf"', '"allOf"')) else [],
            ))
    if not endpoints:
        raise ValueError("No supported API operations were found in the specification.")
    return ApiContract(title=str(info.get("title", "OpenAPI Contract")),
                       base_url=base_url, endpoints=endpoints, source_type="openapi",
                       security_schemes=spec.get("components", {}).get("securitySchemes", {}))


def manual_contract(request: ApiManualRequest) -> ApiContract:
    def params(names: list[str], location: str, required: bool) -> list[ApiParameter]:
        return [ApiParameter(name=name, location=location, required=required) for name in names if name.strip()]

    endpoint = ApiEndpoint(
        method=request.method,
        path=request.path,
        summary=request.summary,
        description=request.description,
        headers=params(request.required_headers, "header", True) + params(request.optional_headers, "header", False),
        query_params=params(request.required_query_params, "query", True) + params(request.optional_query_params, "query", False),
        body_fields=params(request.required_body_fields, "body", True) + params(request.optional_body_fields, "body", False),
        responses=[ApiResponseSpec(status_code=request.success_status, description="Expected success response")]
        + [ApiResponseSpec(status_code=status, description="Expected error response") for status in request.error_statuses],
    )
    return ApiContract(title=request.title, base_url=request.base_url, endpoints=[endpoint], source_type="manual")


def endpoint_choices(contract: ApiContract) -> list[dict[str, str]]:
    return [{
        "key": f"{endpoint.method} {endpoint.path}",
        "label": f"{endpoint.method} {endpoint.path}" + (f" - {endpoint.summary}" if endpoint.summary else ""),
        "method": endpoint.method,
        "path": endpoint.path,
        "summary": endpoint.summary,
        "contract": endpoint.model_dump(),
    } for endpoint in contract.endpoints]


def select_endpoint(contract: ApiContract, endpoint_key: str | None = None) -> ApiEndpoint:
    if endpoint_key:
        for endpoint in contract.endpoints:
            if f"{endpoint.method} {endpoint.path}" == endpoint_key:
                return endpoint
        raise ValueError("Selected endpoint was not found in the API specification.")
    return contract.endpoints[0]
