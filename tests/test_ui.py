import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from openpyxl import load_workbook
from streamlit.testing.v1 import AppTest
from ui.workflow import generate_manual, generate_document
from test_pipeline import ANALYSIS, SCENARIO, CASE


class UiTests(unittest.TestCase):
    def mocks(self):
        stack = contextlib.ExitStack()
        for module, payload in [("requirement_analyzer", ANALYSIS), ("scenario_generator", {"scenarios": [SCENARIO]}), ("test_case_generator", {"test_cases": [CASE]})]:
            stack.enter_context(patch(f"services.{module}.call_llm", return_value=json.dumps(payload)))
        return stack

    def test_manual_workbook(self):
        with self.mocks():
            report = generate_manual("Password length 8 to 20")
        book = load_workbook(io.BytesIO(report["excel_data"]))
        self.assertEqual(book["Traceability"]["A2"].value, "SOURCE-001")
        self.assertEqual(report["processed_count"], 1)
        book.close()

    def test_document_workflow(self):
        extracted = {"requirements": [{"source_id": f"REQ-{i}", "requirement_text": f"Requirement {i}"} for i in range(1, 4)]}
        with self.mocks(), patch("services.requirement_extractor.call_llm", return_value=json.dumps(extracted)):
            report = generate_document("brd.txt", Path("sample_documents/login_brd.txt").read_bytes())
        self.assertEqual(report["processed_count"], 2)
        self.assertEqual(report["extracted_count"], 3)
        self.assertTrue(report["excel_data"].startswith(b"PK"))

    def test_input_errors(self):
        for name, content in [("bad.csv", b"data"), ("empty.txt", b"")]:
            with self.assertRaises(ValueError):
                generate_document(name, content)
        with self.assertRaises(ValueError):
            generate_manual("   ")

    def test_ui_manual_flow_persists_and_clears_on_change(self):
        with patch("ui.api_client.get_history", return_value=[]):
            at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "ui/streamlit_app.py")).run()
        self.assertFalse(at.exception)
        self.assertTrue(at.button[0].disabled)
        at.radio[0].set_value("Enter Requirement").run()
        at.text_area[0].set_value("Password length 8 to 20").run()
        with self.mocks():
            report = generate_manual("Password length 8 to 20")
        saved = {"run_id": "11111111-1111-1111-1111-111111111111", "status": "completed",
                 "stage": "Completed", "result": {k: v for k, v in report.items() if k != "excel_data"}}
        with patch("ui.api_client.get_history", return_value=[]), \
             patch("ui.api_client.submit_manual", return_value=saved), \
             patch("ui.api_client.get_run", return_value=saved), \
             patch("ui.api_client.download_excel", return_value=report["excel_data"]):
            at.button[0].click().run(timeout=20)
        self.assertFalse(at.exception)
        self.assertEqual([m.value for m in at.metric], ["1", "1", "100.0%", "100.0%", "0.0%"])
        self.assertEqual([t.label for t in at.tabs], ["Requirements", "Scenarios", "Test Cases"])
        with patch("ui.api_client.get_history", return_value=[]), \
             patch("ui.api_client.get_run", return_value=saved), \
             patch("ui.api_client.download_excel", return_value=report["excel_data"]):
            at.run()
        self.assertEqual(len(at.metric), 5)
        self.assertTrue(any(button.label == "New run" for button in at.button))

    def test_ui_error_message(self):
        with patch("ui.api_client.get_history", return_value=[]):
            at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "ui/streamlit_app.py")).run()
        at.radio[0].set_value("Enter Requirement").run()
        at.text_area[0].set_value("Password length 8 to 20").run()
        with patch("ui.api_client.get_history", return_value=[]), \
             patch("ui.api_client.submit_manual", side_effect=ValueError("invalid request")):
            at.button[0].click().run()
        self.assertFalse(at.exception)
        self.assertTrue(at.error)
        self.assertEqual(len(at.metric), 0)

    def test_fresh_session_restores_url_run_without_ai_calls(self):
        with self.mocks():
            report = generate_manual("Password length 8 to 20")
        run_id = "22222222-2222-2222-2222-222222222222"
        saved = {"run_id": run_id, "status": "completed", "stage": "Completed",
                 "result": {k: v for k, v in report.items() if k != "excel_data"}}
        at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "ui/streamlit_app.py"))
        at.query_params["run_id"] = run_id
        with patch("ui.api_client.get_history", return_value=[]), \
             patch("ui.api_client.get_run", return_value=saved), \
             patch("ui.api_client.download_excel", return_value=report["excel_data"]), \
             patch("ui.workflow.run_pipeline") as model_path:
            at.run()
            model_path.assert_not_called()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.metric), 5)
        self.assertTrue(any(button.label == "New run" for button in at.button))

