"""Parse model JSON without silently accepting partial or ambiguous output."""

import json
import re


def parse_json_object(response):
    if not isinstance(response, str) or not response.strip():
        raise ValueError("the model returned an empty response")
    text = response.strip().lstrip("\ufeff").strip()
    fence = re.fullmatch(r"```(?:json)?\s*\n?(.*?)\s*```", text,
                         flags=re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"the model returned invalid JSON (line {exc.lineno}, column {exc.colno})"
        ) from exc
    if not isinstance(data, dict):
        raise ValueError("the model must return a JSON object")
    return data


def request_json_object(call, prompt, stage):
    # Retry formatting failures once, without feeding malformed content back in.
    for attempt in range(2):
        response = call(prompt)
        try:
            return parse_json_object(response)
        except ValueError as exc:
            if attempt == 1:
                raise ValueError(
                    f"{stage}: {exc} after 2 attempts. "
                    "Try again or set OPENROUTER_MODEL to another available model."
                ) from exc
            prompt += (
                "\nYour previous response could not be parsed as a JSON object. "
                "Return the complete requested JSON object only, starting with { "
                "and ending with }. No Markdown, preamble or commentary."
            )
