import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from tests.test_api_testing_phase1 import OPENAPI_SPEC
from services.api_spec_parser import parse_openapi_spec
from services.api_test_designer import design_api_tests


class ApiReviewUiTests(unittest.TestCase):
    def test_review_filter_and_export_scope(self):
        contract = parse_openapi_spec(OPENAPI_SPEC)
        plan = design_api_tests(contract, contract.endpoints[0]).model_dump()
        at = AppTest.from_string(
            "import streamlit as st\n"
            "from ui.streamlit_app import _show_api_plan\n"
            "_show_api_plan(st.session_state['plan'])\n")
        at.session_state["plan"] = plan
        with patch("ui.streamlit_app.export_api_tests", return_value=b"test") as export:
            at.run()
            self.assertFalse(at.exception)
            self.assertEqual(export.call_count, 4)
            at.multiselect[0].set_value(["Functional"]).run()
            self.assertFalse(at.exception)
            self.assertEqual(len(export.call_args.args[0]["test_cases"]), 1)
            at.multiselect[0].set_value([]).run()
            self.assertFalse(at.exception)
            self.assertTrue(any("Select at least one" in item.value for item in at.info))

    def test_guided_contract_and_advanced_editor(self):
        endpoint = parse_openapi_spec(OPENAPI_SPEC).endpoints[0].model_dump()
        at = AppTest.from_string(
            "import streamlit as st\n"
            "from ui.streamlit_app import _review_api_endpoint\n"
            "st.session_state['reviewed'] = _review_api_endpoint({'contract': st.session_state['endpoint']})\n")
        at.session_state["endpoint"] = endpoint
        at.run()
        self.assertFalse(at.exception)
        at.text_input[0].set_value("/reviewed").run()
        self.assertEqual(at.session_state["reviewed"]["path"], "/reviewed")
        at.radio[0].set_value("Advanced JSON").run()
        self.assertFalse(at.exception)
        at.text_area[0].set_value("invalid json").run()
        self.assertTrue(at.error)
        self.assertIsNone(at.session_state["reviewed"])


if __name__ == "__main__":
    unittest.main()
