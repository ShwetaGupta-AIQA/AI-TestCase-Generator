import unittest
from pydantic import ValidationError
from models.test_case import TestCaseResponse
from services.generation_errors import validate_model, generation_error_message


class GenerationErrorTests(unittest.TestCase):
    def test_stage_and_fields_without_response_content(self):
        try:
            validate_model(TestCaseResponse, {"test_cases": "PRIVATE CONTENT"}, "Test case generation (SC001)")
        except ValidationError as error:
            message = generation_error_message(error)
        self.assertIn("SC001", message)
        self.assertIn("test_cases", message)
        self.assertNotIn("PRIVATE CONTENT", message)

    def test_json_reason_is_preserved(self):
        message = generation_error_message(ValueError("Scenario generation: invalid JSON after 2 attempts"))
        self.assertIn("Scenario generation", message)
        self.assertIn("invalid JSON", message)

    def test_permission_error(self):
        self.assertIn("File access denied", generation_error_message(PermissionError("private path")))
