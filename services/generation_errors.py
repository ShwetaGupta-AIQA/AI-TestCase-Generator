"""Readable diagnostics without including model output or credentials."""
import os
import re
from pydantic import ValidationError


def validate_model(model, data, stage):
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        exc.generation_stage = stage
        raise


def generation_error_message(error):
    if isinstance(error, ValidationError):
        stage = getattr(error, "generation_stage", "Generated output validation")
        issues = []
        for item in error.errors(include_input=False, include_context=False, include_url=False)[:5]:
            location = ".".join(str(part) for part in item["loc"])
            issues.append(f"{location}: {item['type']}")
        message = f"{stage}: the AI response does not match the required schema. " + "; ".join(issues)
    elif isinstance(error, PermissionError):
        message = "File access denied while reading the upload or writing the Excel export. Check temporary-folder permissions and close any open output workbook."
    elif isinstance(error, OSError):
        message = f"Document or Excel file operation failed ({type(error).__name__}). Check available disk space and file permissions."
    else:
        message = str(error)
    key = os.getenv("OPENROUTER_API_KEY", "")
    if key:
        message = message.replace(key, "[redacted]")
    return re.sub(r"sk-or-v1-[A-Za-z0-9_-]+", "[redacted]", message)[:1500]
