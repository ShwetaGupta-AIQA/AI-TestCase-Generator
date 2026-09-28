import os
import unittest
from unittest.mock import MagicMock, patch

from services.llm_service import call_llm


class LlmServiceTests(unittest.TestCase):
    def test_requests_json_mode_from_openrouter(self):
        response = MagicMock()
        response.choices = [MagicMock(message=MagicMock(content='{"value": 1}'))]
        client = MagicMock()
        client.chat.completions.create.return_value = response
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=False), \
             patch("services.llm_service.OpenAI") as openai:
            openai.return_value.__enter__.return_value = client
            self.assertEqual(call_llm("Return JSON"), '{"value": 1}')
        self.assertEqual(client.chat.completions.create.call_args.kwargs["response_format"],
                         {"type": "json_object"})


if __name__ == "__main__":
    unittest.main()
