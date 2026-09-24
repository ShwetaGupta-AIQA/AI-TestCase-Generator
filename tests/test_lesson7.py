import contextlib
import io
import json
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from app import run_pipeline
from models.requirement import BoundaryConstraint
from qa_engine.boundary_analyzer import generate_boundary_values
from utils.id_generator import IDGenerator
from test_pipeline import ANALYSIS, SCENARIO, CASE


class Lesson7Tests(unittest.TestCase):
    def test_id_sequences_and_reset(self):
        generator = IDGenerator()
        self.assertEqual(generator.next_requirement_id(), "REQ001")
        self.assertEqual([generator.next_scenario_id() for _ in range(3)],
                         ["SC001", "SC002", "SC003"])
        self.assertEqual([generator.next_test_case_id() for _ in range(4)],
                         ["TC001", "TC002", "TC003", "TC004"])
        self.assertEqual(IDGenerator().next_test_case_id(), "TC001")

    def test_password_boundaries(self):
        values = generate_boundary_values(8, 20)
        self.assertEqual([v["value"] for v in values], [7, 8, 9, 19, 20, 21])
        self.assertEqual([v["expected_valid"] for v in values],
                         [False, True, True, True, True, False])

    def test_equal_limits_do_not_mark_outside_values_valid(self):
        for boundary in generate_boundary_values(8, 8):
            self.assertEqual(boundary["expected_valid"], boundary["value"] == 8)

    def test_invalid_limits(self):
        for minimum, maximum in [(20, 8), (None, 20), (8.5, 20), (True, 20)]:
            with self.subTest(minimum=minimum), self.assertRaises(ValueError):
                generate_boundary_values(minimum, maximum)
        with self.assertRaises(ValidationError):
            BoundaryConstraint(field="length", minimum=20, maximum=8, unit="characters")

    def test_pipeline_boundaries_and_one_sided_limit(self):
        for minimum in [8, None]:
            boundary = dict(field="password_length", minimum=minimum,
                            maximum=20, unit="characters")
            with self.subTest(minimum=minimum), contextlib.ExitStack() as stack:
                for module, payload in [
                    ("requirement_analyzer", dict(ANALYSIS, boundary_constraints=[boundary])),
                    ("scenario_generator", {"scenarios": [SCENARIO]}),
                    ("test_case_generator", {"test_cases": [CASE]}),
                ]:
                    stack.enter_context(patch(f"services.{module}.call_llm", return_value=json.dumps(payload)))
                output = stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
                result = run_pipeline("Password must contain between 8 and 20 characters.")
                report = result["boundary_analysis"][0]
                self.assertEqual(report["minimum"], minimum)
                self.assertTrue(result["test_cases"])
                if minimum is None:
                    self.assertEqual(report["boundary_values"], [])
                    self.assertIn("BVA skipped", output.getvalue())
                else:
                    self.assertEqual([v["value"] for v in report["boundary_values"]],
                                     [7, 8, 9, 19, 20, 21])
                    self.assertIn("7 -> below_minimum -> Valid: False", output.getvalue())
