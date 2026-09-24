import unittest

from pydantic import ValidationError

from models.test_case import TestCaseResponse
from test_pipeline import CASE


class TestDataTests(unittest.TestCase):
    def test_empty_and_whitespace_inputs_are_preserved(self):
        for password in ["", " ", "   ", " password "]:
            with self.subTest(password=repr(password)):
                response = TestCaseResponse.model_validate({"test_cases": [
                    CASE,
                    dict(CASE, test_case_id="TC002", test_type="Negative",
                         test_data={"password": password}),
                ]})
                self.assertEqual(response.test_cases[1].test_data["password"], password)

    def test_descriptive_fields_are_checked_by_qa_validator(self):
        from qa_engine.test_case_validator import validate_test_case
        for field, value in [("title", ""), ("expected_result", " "), ("steps", [""])]:
            case = TestCaseResponse.model_validate({"test_cases": [dict(CASE, **{field: value})]}).test_cases[0]
            self.assertFalse(validate_test_case(case, "REQ001", "SC001")["valid"])

    def test_test_data_values_still_require_strings(self):
        with self.assertRaises(ValidationError):
            TestCaseResponse.model_validate({"test_cases": [
                dict(CASE, test_data={"password": None})
            ]})
