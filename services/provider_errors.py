"""Safe, actionable provider diagnostics without exposing response bodies."""
from openai import APIConnectionError, APITimeoutError


def daily_quota_exhausted(error):
    body = getattr(error, "body", None)
    return getattr(error, "status_code", None) == 429 and "free-models-per-day" in str(body)


def provider_error_message(error):
    if daily_quota_exhausted(error):
        return ("OpenRouter's daily free-model request limit has been reached (HTTP 429). "
                "Wait for the quota to reset, or review your OpenRouter account's credits and limits. "
                "Retrying now will not help.")
    status = getattr(error, "status_code", None)
    if isinstance(error, APITimeoutError):
        return "The AI provider timed out. Retry later or choose another available model."
    if isinstance(error, APIConnectionError):
        return "Could not connect to OpenRouter. Check your internet connection, proxy and firewall."
    return {
        401: "OpenRouter rejected the API key (HTTP 401). Check OPENROUTER_API_KEY and restart the app after changing .env.",
        402: "OpenRouter reports insufficient credits (HTTP 402). Check your account balance and spending limits.",
        403: "OpenRouter denied this request (HTTP 403). Check account permissions and provider restrictions.",
        404: "The configured model or endpoint is unavailable (HTTP 404). Check OPENROUTER_MODEL.",
        429: "OpenRouter is rate limiting requests (HTTP 429). Wait before retrying and check your account limits.",
    }.get(status, f"AI provider request failed (HTTP {status or 'unknown'}). Check provider availability and retry later.")
