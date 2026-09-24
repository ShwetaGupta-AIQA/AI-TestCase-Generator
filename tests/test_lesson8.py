import contextlib
import io
import json
import unittest
from unittest.mock import patch

from app import run_pipeline
from models.test_case import TestCase
from qa_engine.test_case_validator import validate_test_case, find_duplicate_titles
from test_pipeline import ANALYSIS, SCENARIO, CASE


class Lesson8Tests(unittest.TestCase):
    def test_deliberately_bad_case(self):
        case = TestCase(**dict(CASE, title="", steps=[], expected_result="",
                              requirement_id="wrong", scenario_id="wrong", test_data={}))
        report = validate_test_case(case, "REQ001", "SC001")
        self.assertFalse(report["valid"])
        self.assertEqual(len(report["errors"]), 5)
        self.assertEqual(report["warnings"], ["No test data was generated."])

    def test_empty_password_is_not_missing_data(self):
        case = TestCase(**dict(CASE, test_data={"password": ""}))
        self.assertEqual(validate_test_case(case, "REQ001", "SC001"),
                         {"valid": True, "errors": [], "warnings": []})

    def test_duplicates_ignore_case_and_outer_whitespace(self):
        cases = [TestCase(**dict(CASE, title=title, test_case_id=f"TC{i}"))
                 for i, title in enumerate([" Check Password ", "check password", "Other", "CHECK PASSWORD"])]
        self.assertEqual(find_duplicate_titles(cases), ["TC1", "TC3"])

    def test_pipeline_owns_ids_and_reports_rejections(self):
        for _ in range(2):
            with contextlib.ExitStack() as stack:
                stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
                stack.enter_context(patch("services.requirement_analyzer.call_llm", return_value=json.dumps(dict(ANALYSIS, requirement_id="REQ934"))))
                stack.enter_context(patch("services.scenario_generator.call_llm", return_value=json.dumps({"scenarios": [dict(SCENARIO, scenario_id="repeated", requirement_id="wrong")] * 2})))
                stack.enter_context(patch("services.test_case_generator.call_llm", side_effect=[
                    json.dumps({"test_cases": [dict(CASE, requirement_id="wrong", scenario_id="wrong"), dict(CASE, title="", steps=[], expected_result="")]}),
                    json.dumps({"test_cases": [dict(CASE, requirement_id="wrong", scenario_id="wrong")]}),
                ]))
                result = run_pipeline("Password length is 8 to 20 characters")
            self.assertEqual(result["analysis"]["requirement_id"], "REQ001")
            self.assertEqual([s["scenario_id"] for s in result["scenarios"]], ["SC001", "SC002"])
            self.assertEqual([c["test_case_id"] for c in result["test_cases"]], ["TC001", "TC003"])
            self.assertEqual(result["rejected_test_cases"][0]["test_case_id"], "TC002")
            self.assertEqual(result["test_cases"][1]["scenario_id"], "SC002")
            self.assertTrue(all(c["requirement_id"] == "REQ001" for c in result["test_cases"]))
            self.assertEqual(result["duplicate_test_case_ids"], ["TC003"])
            self.assertEqual(result["validation_summary"], dict(total_test_cases=3, valid_test_cases=2, invalid_test_cases=1, exact_duplicates=1))
