import unittest
from unittest.mock import patch

from models.test_case import TestCase
from models.test_scenario import TestScenario
from models.requirement import RequirementAnalysis, BoundaryConstraint
from evaluation.evaluator import evaluate_test_suite, evaluate_boundary_extraction
from run_evaluation import run_evaluation
from test_pipeline import CASE, SCENARIO, ANALYSIS


class EvaluationTests(unittest.TestCase):
    def test_duplicates_and_completeness(self):
        cases = [TestCase(**CASE), TestCase(**dict(CASE, title=CASE["title"].upper(), steps=[" "]))]
        result = evaluate_test_suite(cases)
        self.assertEqual(result.duplicate_rate, 50)
        self.assertEqual(result.completeness_score, 50)
        self.assertEqual(result.duplicate_test_cases, 1)

    def test_real_mapping_checks(self):
        cases = [TestCase(**CASE), TestCase(**dict(CASE, requirement_id="wrong")),
                 TestCase(**dict(CASE, scenario_id="unknown"))]
        result = evaluate_test_suite(cases, [TestScenario(**SCENARIO)])
        self.assertEqual(result.traceable_test_cases, 1)
        self.assertEqual(result.traceability_score, 33.33)

    def test_empty_suite(self):
        result = evaluate_test_suite([])
        self.assertEqual(result.completeness_score, 0)
        self.assertTrue(result.issues)

    def test_boundary_extraction(self):
        analysis = RequirementAnalysis(**ANALYSIS)
        self.assertTrue(evaluate_boundary_extraction(analysis, None, None, None))
        self.assertFalse(evaluate_boundary_extraction(analysis, 8, 20, "characters"))
        boundary = BoundaryConstraint(field="size", minimum=None, maximum=10, unit="MB")
        analysis.boundary_constraints = [boundary]
        self.assertTrue(evaluate_boundary_extraction(analysis, None, 10, "mb"))
        self.assertFalse(evaluate_boundary_extraction(analysis, None, None, None))
        analysis.boundary_constraints = [boundary, boundary]
        self.assertFalse(evaluate_boundary_extraction(analysis, None, 10, "MB"))

    def test_golden_runner_continues_after_failure(self):
        password = RequirementAnalysis(**dict(ANALYSIS, boundary_constraints=[dict(field="password_length", minimum=8, maximum=20, unit="characters")]))
        with patch("run_evaluation.analyze_requirement", side_effect=[password, ValueError("invalid JSON"), RequirementAnalysis(**ANALYSIS)]):
            report = run_evaluation()
        self.assertEqual(report["total"], 3)
        self.assertEqual(report["passed"], 1)
        self.assertEqual(report["boundary_extraction_accuracy"], 33.33)
        self.assertEqual(report["schema_validity_score"], 66.67)
        self.assertEqual(report["results"][1]["error"], "ValueError")
