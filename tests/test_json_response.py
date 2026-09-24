import json
import unittest
from unittest.mock import Mock, patch

from services.json_response import parse_json_object, request_json_object
from services.scenario_generator import generate_scenarios
from test_pipeline import ANALYSIS, SCENARIO
from models.requirement import RequirementAnalysis


class JsonResponseTests(unittest.TestCase):
    def test_json_and_fences(self):
        for response in ['{"value": 1}', '\ufeff{"value": 1}',
                         '```json\n{"value": 1}\n```',
                         '```\n{"value": 1}\n```']:
            with self.subTest(response=response):
                self.assertEqual(parse_json_object(response), {"value": 1})

    def test_reject_invalid_or_partial_output(self):
        for response in [None, "", "  ", "Not JSON", '{"value":',
                         '[]', 'null', '{} {}', 'Explanation: {}']:
            with self.subTest(response=response), self.assertRaises(ValueError):
                parse_json_object(response)

    def test_retry_recovers(self):
        call = Mock(side_effect=["", '{"value": 1}'])
        self.assertEqual(request_json_object(call, "prompt", "Scenarios"), {"value": 1})
        self.assertEqual(call.call_count, 2)

    def test_failure_is_bounded_and_names_stage(self):
        call = Mock(return_value="Not JSON")
        with self.assertRaisesRegex(ValueError, "Scenario generation:.*after 2 attempts"):
            request_json_object(call, "prompt", "Scenario generation")
        self.assertEqual(call.call_count, 2)

    def test_scenario_markdown_regression(self):
        response = '```json\n' + json.dumps({"scenarios": [SCENARIO]}) + '\n```'
        with patch("services.scenario_generator.call_llm", return_value=response) as call:
            result = generate_scenarios(RequirementAnalysis(**ANALYSIS))
        self.assertEqual(result.scenarios[0].scenario_id, "SC001")
        call.assert_called_once()

    def test_schema_validation_is_preserved(self):
        with patch("services.scenario_generator.call_llm", return_value='```json\n{}\n```'):
            with self.assertRaises(ValueError):
                generate_scenarios(RequirementAnalysis(**ANALYSIS))
