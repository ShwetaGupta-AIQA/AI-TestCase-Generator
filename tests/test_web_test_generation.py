import json
import unittest
import zipfile
from io import BytesIO
from unittest.mock import patch

from models.web_testing import WebPageElement, WebPageSnapshot
from services.web_test_exporter import export_playwright_pytest
from services.web_test_generator import generate_web_ui_tests


class WebTestGenerationTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = WebPageSnapshot(
            url="https://example.com/login",
            title="Account sign in",
            headings=["Sign in", "Welcome"],
            elements=[
                WebPageElement(role="textbox", name="Email address"),
                WebPageElement(role="button", name="Continue"),
                WebPageElement(role="textbox", name="Password", locator_strategy="placeholder"),
                WebPageElement(role="checkbox", name="onion"),
            ],
        )

    def _response(self, locator_name="Email address", locator_role="textbox", first_action="fill"):
        return json.dumps({"test_cases": [{
            "title": "User can submit sign in details",
            "test_type": "Functional",
            "priority": "High",
            "objective": "Check the sign in form accepts entered credentials.",
            "preconditions": ["The sign in page is loaded"],
            "actions": [
                {"action": first_action, "locator": {"strategy": "role", "role": locator_role,
                                                       "value": locator_name},
                 "value": "user@example.test"},
                {"action": "click", "locator": {"strategy": "role", "role": "button",
                                                       "value": "Continue"}},
            ],
            "assertions": [{"kind": "visible", "value": "visible",
                            "locator": {"strategy": "text", "value": "Welcome"}}],
        }]})

    @patch("services.web_test_generator.call_llm")
    def test_generates_plan_with_assigned_ids(self, call_llm):
        call_llm.return_value = self._response()
        plan = generate_web_ui_tests(self.snapshot, "User can sign in")
        self.assertEqual(plan.test_cases[0].test_case_id, "WEB-TC-001")
        self.assertEqual(plan.snapshot.title, "Account sign in")
        self.assertEqual(call_llm.call_count, 1)

    @patch("services.web_test_generator.call_llm")
    def test_repairs_nested_action_object_from_model(self, call_llm):
        malformed = json.loads(self._response())
        malformed["test_cases"][0]["actions"].append({
            "action": {
                "action": "check",
                "locator": {"strategy": "role", "role": "checkbox", "value": "onion"},
            },
        })
        call_llm.return_value = json.dumps(malformed)
        plan = generate_web_ui_tests(self.snapshot, "User can sign in")
        checkbox_action = plan.test_cases[0].actions[-1]
        self.assertEqual(checkbox_action.action, "check")
        self.assertEqual(checkbox_action.locator.value, "onion")

    @patch("services.web_test_generator.call_llm")
    def test_rejects_locators_not_present_on_inspected_page(self, call_llm):
        call_llm.return_value = self._response("Admin console")
        with self.assertRaisesRegex(ValueError, "not found on the inspected page"):
            generate_web_ui_tests(self.snapshot, "User can sign in")

    @patch("services.web_test_generator.call_llm")
    def test_retries_once_when_action_does_not_match_observed_role(self, call_llm):
        call_llm.side_effect = [self._response(first_action="click"), self._response()]
        plan = generate_web_ui_tests(self.snapshot, "User can sign in")
        self.assertEqual(plan.test_cases[0].test_case_id, "WEB-TC-001")
        self.assertEqual(call_llm.call_count, 2)
        self.assertIn("Action-role rules", call_llm.call_args.args[0])

    @patch("services.web_test_generator.call_llm")
    def test_schema_error_uses_same_single_correction_attempt(self, call_llm):
        malformed = json.loads(self._response())
        malformed["test_cases"][0]["unexpected"] = "extra field"
        call_llm.side_effect = [json.dumps(malformed), self._response()]
        plan = generate_web_ui_tests(self.snapshot, "User can sign in")
        self.assertEqual(plan.test_cases[0].test_case_id, "WEB-TC-001")
        self.assertEqual(call_llm.call_count, 2)
        self.assertIn("test_cases.0.unexpected: extra_forbidden", call_llm.call_args.args[0])

    @patch("services.web_test_generator.call_llm")
    def test_reports_action_and_control_when_corrective_retry_still_fails(self, call_llm):
        call_llm.side_effect = [self._response(first_action="click")] * 2
        with self.assertRaisesRegex(ValueError, "action 'click'.*control 'Email address'"):
            generate_web_ui_tests(self.snapshot, "User can sign in")
        self.assertEqual(call_llm.call_count, 2)

    @patch("services.web_test_generator.call_llm")
    def test_export_contains_compilable_reviewable_playwright_tests(self, call_llm):
        call_llm.return_value = self._response()
        plan = generate_web_ui_tests(self.snapshot, "User can sign in")
        output = BytesIO(export_playwright_pytest(plan))
        with zipfile.ZipFile(output) as archive:
            source = archive.read("test_web_ui.py").decode("utf-8")
            compile(source, "test_web_ui.py", "exec")
            self.assertIn("page.get_by_role(\"textbox\", name=\"Email address\", exact=True).fill", source)
            self.assertIn("page.get_by_text(\"Welcome\", exact=True)", source)
            self.assertIn("# Preconditions: The sign in page is loaded", source)
            self.assertIn("executed by TestGen AI", archive.read("README.md").decode("utf-8"))


if __name__ == "__main__":
    unittest.main()