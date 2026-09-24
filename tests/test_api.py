import json
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from api.main import app
from services.document_reader import read_document
from test_pipeline import ANALYSIS, SCENARIO, CASE


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_health_docs_and_schema(self):
        self.assertEqual(self.client.get("/health").json(), {"status": "healthy"})
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/docs").status_code, 200)
        paths = self.client.get("/openapi.json").json()["paths"]
        self.assertIn("/upload-document", paths)
        self.assertIn("/generate-test-cases", paths)

    def test_bad_input_never_calls_model(self):
        for route in ["/analyze-requirement", "/generate-scenarios", "/generate-test-cases"]:
            for body in [{}, {"requirement": "     "}, {"requirement": "abcd"}, {"requirement": 123}]:
                with self.subTest(route=route, body=body), patch("services.llm_service.OpenAI") as call:
                    self.assertEqual(self.client.post(route, json=body).status_code, 422)
                    call.assert_not_called()

    def test_analysis_scenarios_and_full_pipeline(self):
        with patch("services.requirement_analyzer.call_llm", return_value=json.dumps(ANALYSIS)), patch("services.scenario_generator.call_llm", return_value=json.dumps({"scenarios": [SCENARIO]})), patch("services.test_case_generator.call_llm", return_value=json.dumps({"test_cases": [CASE]})):
            payload = {"requirement": "Password length is 8 to 20 characters"}
            self.assertEqual(self.client.post("/analyze-requirement", json=payload).json()["requirement_id"], "REQ001")
            self.assertEqual(self.client.post("/generate-scenarios", json=payload).json()["scenarios"][0]["scenario_id"], "SC001")
            result = self.client.post("/generate-test-cases", json=payload)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()["requirement"]["requirement_id"], "REQ001")
            self.assertEqual(result.json()["test_cases"][0]["test_case_id"], "TC001")
            self.assertEqual(result.json()["validation_summary"]["valid_test_cases"], 1)

    def test_upload_and_cleanup(self):
        paths = []
        def reader(path):
            paths.append(path)
            return read_document(path)
        extracted = {"requirements": [{"source_id": f"REQ-{i}", "requirement_text": f"Requirement {i}"} for i in range(1, 5)]}
        with patch("api.main.read_document", side_effect=reader), patch("services.requirement_extractor.call_llm", return_value=json.dumps(extracted)):
            response = self.client.post("/upload-document", files={"file": ("login_brd.txt", Path("sample_documents/login_brd.txt").read_bytes())})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["requirements_found"], 4)
        self.assertTrue(paths)
        self.assertFalse(paths[0].parent.exists())

    def test_bad_uploads(self):
        for name, content, status in [("bad.csv", b"abc", 400), ("empty.txt", b"", 400), ("bad.pdf", b"invalid", 400)]:
            with self.subTest(name=name), patch("api.main.extract_requirements") as call:
                self.assertEqual(self.client.post("/upload-document", files={"file": (name, content)}).status_code, status)
                call.assert_not_called()
        with patch("api.main.MAX_UPLOAD_BYTES", 2):
            self.assertEqual(self.client.post("/upload-document", files={"file": ("large.txt", b"123")}).status_code, 413)

    def test_generation_errors_are_sanitized(self):
        with patch("api.main.analyze_requirement", side_effect=ValueError("private response")):
            result = self.client.post("/analyze-requirement", json={"requirement": "Some requirement"})
        self.assertEqual(result.status_code, 502)
        self.assertNotIn("private response", result.text)
