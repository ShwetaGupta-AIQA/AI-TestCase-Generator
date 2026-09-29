"""Concrete field mutations derived only from documented constraints."""
from jsonschema import Draft202012Validator


def boundary_values(schema):
    candidates = []
    kind = schema.get("type")
    if kind == "integer":
        for key in ("minimum", "maximum"):
            limit = schema.get(key)
            if isinstance(limit, int) and not isinstance(limit, bool):
                candidates.extend((f"{key} {offset:+d}", limit + offset) for offset in (-1, 0, 1))
    if kind == "string":
        for key in ("minLength", "maxLength"):
            limit = schema.get(key)
            if isinstance(limit, int) and 0 <= limit <= 4096:
                candidates.extend((f"{key} {offset:+d}", "x" * (limit + offset))
                                  for offset in (-1, 0, 1) if limit + offset >= 0)
    if schema.get("enum"):
        candidates.extend(("allowed enum value", value) for value in schema["enum"][:20])
        outside = "__outside_enum__"
        while outside in schema["enum"]:
            outside += "_"
        candidates.append(("outside enum", outside))
    # Pattern, format and composed schema support needs richer example generation.
    if any(key in schema for key in ("$ref", "oneOf", "anyOf", "allOf", "pattern", "format")):
        return []
    try:
        Draft202012Validator.check_schema(schema)
    except Exception:
        return []
    validator = Draft202012Validator(schema)
    seen = set()
    result = []
    for label, value in candidates:
        identity = repr(value)
        if identity not in seen:
            seen.add(identity)
            result.append((label, value, validator.is_valid(value)))
    return result
