import unittest
import httpx
from openai import RateLimitError, AuthenticationError
from services.provider_errors import provider_error_message

class ProviderErrorTests(unittest.TestCase):
    def test_daily_quota(self):
        response = httpx.Response(429, request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"))
        error = RateLimitError("private detail", response=response, body={"message": "Rate limit exceeded: free-models-per-day"})
        message = provider_error_message(error)
        self.assertIn("daily free-model", message)
        self.assertNotIn("private detail", message)

    def test_invalid_key(self):
        response = httpx.Response(401, request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"))
        error = AuthenticationError("secret", response=response, body={})
        self.assertIn("HTTP 401", provider_error_message(error))
        self.assertNotIn("secret", provider_error_message(error))
