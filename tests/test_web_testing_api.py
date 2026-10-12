import json
import unittest
import zipfile
from io import BytesIO
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app
from models.web_testing import (WebPageElement, WebPageSnapshot, WebUITestCase,
                                WebUITestPlan, WebUIAssertion, WebLocator)


class WebTestingApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.snapshot = WebPageSnapshot(
            url="https://example.com/login", title="Sign in", headings=["Welcome"],
            elements=[WebPageElement(role="button", name="Continue")],
        )
        self.plan = WebUITestPlan(
            url=self.snapshot.url, page_title=self.snapshot.title,
            user_goal="Check the sign in page", snapshot=self.snapshot,
            test_cases=[WebUITestCase(
                test_case_id="WEB-TC-001", title="Continue button is visible",
                test_type="Functional", priority="Medium",
                objective="Verify the sign in page exposes its continue action.",
                actions=[], assertions=[WebUIAssertion(
                    kind="visible", value="visible",
                    locator=WebLocator(strategy="role", role="button", value="Continue"),
                )],
            )],
        )
        self.draft_json = json.dumps({
            "test_cases": [{
                "title": "Continue button is visible", "test_type": "Functional",
                "priority": "Medium",
                "objective": "Verify the sign in page exposes its continue action.",
                "actions": [],
                "assertions": [{"kind": "visible", "value": "visible",
                                "locator": {"strategy": "role", "role": "button", "value": "Continue"}}],
            }],
        })

    def test_generate_route_inspects_page_and_returns_plan(self):
        with patch("api.main.inspect_public_page", return_value=self.snapshot), \
                patch("services.web_test_generator.call_llm", return_value=self.draft_json):
            response = self.client.post("/web-testing/generate", json={
                "url": self.snapshot.url, "user_goal": "Check the sign in page",
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["test_cases"][0]["test_case_id"], "WEB-TC-001")

    def test_rendered_generation_is_disabled_by_default(self):
        with patch("api.main.rendered_inspection_enabled", return_value=False), \
                patch("api.main.inspect_rendered_public_page") as inspect:
            response = self.client.post("/web-testing/generate", json={
                "url": self.snapshot.url, "user_goal": "Check the sign in page",
                "inspection_mode": "rendered",
            })
        self.assertEqual(response.status_code, 503)
        self.assertIn("TESTGEN_ENABLE_RENDERED_INSPECTION", response.json()["detail"])
        inspect.assert_not_called()

    def test_rendered_generation_uses_rendered_inspector_when_enabled(self):
        with patch("api.main.rendered_inspection_enabled", return_value=True), \
                patch("api.main.inspect_rendered_public_page", return_value=self.snapshot) as inspect, \
                patch("services.web_test_generator.call_llm", return_value=self.draft_json):
            response = self.client.post("/web-testing/generate", json={
                "url": self.snapshot.url, "user_goal": "Check the sign in page",
                "inspection_mode": "rendered",
            })
        self.assertEqual(response.status_code, 200)
        inspect.assert_called_once_with(self.snapshot.url)

    def test_generate_route_returns_actionable_url_error(self):
        with patch("api.main.inspect_public_page", side_effect=ValueError("Private or local web pages are not supported.")):
            response = self.client.post("/web-testing/generate", json={
                "url": self.snapshot.url, "user_goal": "Check the sign in page",
            })
        self.assertEqual(response.status_code, 422)
        self.assertIn("Private or local", response.json()["detail"])

    def test_export_route_returns_playwright_zip(self):
        response = self.client.post("/web-testing/export/playwright", json=self.plan.model_dump())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/zip")
        with zipfile.ZipFile(BytesIO(response.content)) as archive:
            compile(archive.read("test_web_ui.py"), "test_web_ui.py", "exec")

    def test_export_route_rejects_unobserved_locator(self):
        plan = self.plan.model_dump()
        plan["test_cases"][0]["assertions"][0]["locator"]["value"] = "Delete account"
        response = self.client.post("/web-testing/export/playwright", json=plan)
        self.assertEqual(response.status_code, 422)

    def test_generation_rejects_non_https_url_at_request_validation(self):
        response = self.client.post("/web-testing/generate", json={
            "url": "http://example.com", "user_goal": "Check the sign in page",
        })
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()