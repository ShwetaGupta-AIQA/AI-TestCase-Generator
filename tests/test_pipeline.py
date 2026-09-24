import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import main, run_pipeline
from models.requirement import RequirementAnalysis
from models.test_scenario import TestScenario
from services.requirement_analyzer import analyze_requirement
from services.scenario_generator import generate_scenarios
from services.test_case_generator import generate_test_cases
from services.llm_service import call_llm

ANALYSIS = dict(requirement_id="REQ001", actor="User", functionality="Create password",
                business_rules=["Password length is 8 to 20 characters"],
                constraints=["8 to 20 characters"], boundary_constraints=[], missing_information=[],
                assumptions=[], clarification_questions=[])
SCENARIO = dict(scenario_id="SC001", requirement_id="REQ001", title="Valid length",
                scenario_type="Functional", description="Accept a valid password length")
CASE = dict(test_case_id="TC001", requirement_id="REQ001", scenario_id="SC001",
            title="Accept eight characters", test_type="Functional", priority="High",
            preconditions=[], steps=["Enter an eight-character password"],
            test_data={"password": "abcdefgh"}, expected_result="Length is accepted")

class PipelineTests(unittest.TestCase):
    def mocks(self):
        stack = contextlib.ExitStack()
        for module, payload in [("requirement_analyzer", ANALYSIS),
                                ("scenario_generator", {"scenarios": [SCENARIO]}),
                                ("test_case_generator", {"test_cases": [CASE]})]:
            stack.enter_context(patch(f"services.{module}.call_llm", return_value=json.dumps(payload)))
        return stack

    def test_pipeline(self):
        with self.mocks():
            result = run_pipeline("Password length is 8 to 20 characters")
        self.assertEqual(result["test_cases"][0]["scenario_id"], result["scenarios"][0]["scenario_id"])
        self.assertEqual(result["analysis"], ANALYSIS)

    def test_cli_file_and_export(self):
        with tempfile.TemporaryDirectory() as directory, self.mocks():
            source = Path(directory) / "input.txt"
            source.write_text("Password length is 8 to 20 characters", encoding="utf-8")
            output = Path(directory) / "nested" / "result.json"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["--file", str(source), "--output", str(output)]), 0)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), json.loads(stdout.getvalue()))

    def test_empty_input_does_not_call_provider(self):
        with patch("services.requirement_analyzer.call_llm") as provider:
            with self.assertRaises(ValueError):
                analyze_requirement("   ")
            provider.assert_not_called()

    def test_invalid_json(self):
        with patch("services.requirement_analyzer.call_llm", return_value="not json"):
            with self.assertRaises(ValueError):
                analyze_requirement("requirement")

    def test_invalid_scenarios(self):
        for entries in [[dict(SCENARIO, scenario_type="unknown")], []]:
            with self.subTest(entries=entries), patch("services.scenario_generator.call_llm", return_value=json.dumps({"scenarios": entries})):
                with self.assertRaises(ValueError):
                    generate_scenarios(RequirementAnalysis(**ANALYSIS))

    def test_invalid_test_cases(self):
        scenario = TestScenario(**SCENARIO)
        for entries in [[dict(CASE, test_type="unknown")], [dict(CASE, steps="wrong type")], []]:
            with self.subTest(entries=entries), patch("services.test_case_generator.call_llm", return_value=json.dumps({"test_cases": entries})):
                with self.assertRaises(ValueError):
                    generate_test_cases(RequirementAnalysis(**ANALYSIS), scenario)

    def test_multiple_scenarios_have_unique_case_ids(self):
        second = dict(SCENARIO, scenario_id="SC002")
        with self.mocks():
            with patch("services.scenario_generator.call_llm", return_value=json.dumps({"scenarios": [SCENARIO, second]})), patch("services.test_case_generator.call_llm", side_effect=[json.dumps({"test_cases": [CASE]}), json.dumps({"test_cases": [dict(CASE, scenario_id="SC002")]})]) as provider:
                result = run_pipeline("Password length is 8 to 20 characters")
        self.assertEqual(provider.call_count, 2)
        self.assertEqual([c["test_case_id"] for c in result["test_cases"]], ["TC001", "TC002"])
        self.assertEqual([c["scenario_id"] for c in result["test_cases"]], ["SC001", "SC002"])

    def test_scenario_requirement_mismatch_before_api(self):
        with patch("services.test_case_generator.call_llm") as provider:
            with self.assertRaises(ValueError):
                generate_test_cases(RequirementAnalysis(**ANALYSIS), TestScenario(**dict(SCENARIO, requirement_id="other")))
            provider.assert_not_called()

    def test_interactive_display(self):
        with self.mocks(), patch("builtins.input", return_value="Password length is 8 to 20 characters"), contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main([]), 0)
        self.assertIn("GENERATED TEST CASES", stdout.getvalue())
        self.assertIn("Accept eight characters", stdout.getvalue())

    def test_missing_api_key(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}), patch("services.llm_service.OpenAI") as client:
            with self.assertRaisesRegex(ValueError, "OPENROUTER_API_KEY"):
                call_llm("test")
            client.assert_not_called()

    def test_cli_error(self):
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(main(["--requirement", " "]), 1)
        self.assertIn("Requirement must not be empty", stderr.getvalue())

if __name__ == "__main__":
    unittest.main()
