"""Public UI configuration; never expose provider secrets or workspace credentials."""
import os


def capabilities(*, demo=False):
    if demo:
        from services.demo_limits import MAX_UPLOAD_BYTES, MAX_TEXT_CHARS
        upload_bytes, text_chars = MAX_UPLOAD_BYTES, MAX_TEXT_CHARS
    else:
        upload_bytes, text_chars = 10 * 1024 * 1024, None
    return {
        "mode": "demo" if demo else "durable",
        "features": {
            "requirements": True, "documents": True,
            "api_testing": not demo, "web_testing": not demo, "history": not demo,
            "rendered_inspection": not demo and os.getenv("TESTGEN_ENABLE_RENDERED_INSPECTION", "false").lower() == "true",
        },
        "workspace_required": not demo and os.getenv("TESTGEN_REQUIRE_WORKSPACE", "false").lower() == "true",
        "limits": {"upload_bytes": upload_bytes, "requirement_chars": text_chars},
    }
