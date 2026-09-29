"""Execute exported Python functions with a controlled HTTP transport."""
import sys
import json
from urllib.parse import parse_qs, urlsplit
import types
import unittest
import zipfile
import requests
from io import BytesIO
from unittest.mock import patch

from models.api_testing import ApiManualRequest
from services.api_spec_parser import manual_contract
from services.api_test_designer import design_api_tests
from services.api_test_exporter import export_pytest_suite, export_postman_collection


class ExportExecutionTests(unittest.TestCase):
    def test_postman_url_headers_and_unconfirmed_case(self):
        contract = manual_contract(ApiManualRequest(method="POST", path="/items", success_status="201",
            required_body_fields=["name"], required_query_params=["search"], base_url="https://test.example.com/"))
        plan = design_api_tests(contract, contract.endpoints[0])
        plan.test_cases[0].query_params = {"search": "a & b/+?"}
        exported = json.loads(export_postman_collection(plan))
        self.assertEqual(exported["variable"][0]["value"], "https://test.example.com")
        request = exported["item"][0]["request"]
        self.assertEqual(parse_qs(urlsplit(request["url"]).query), {"search": ["a & b/+?"]})
        self.assertIn({"key": "Content-Type", "value": "application/json"}, request["header"])
        events = exported["item"][1]["event"]
        self.assertEqual(events[0]["listen"], "prerequest")
        self.assertIn("pm.execution.skipRequest();", events[0]["script"]["exec"])

    def load_export(self):
        contract = manual_contract(ApiManualRequest(method="POST", path="/items", success_status="201",
                                                    required_body_fields=["name"], base_url="https://test.example.com"))
        plan = design_api_tests(contract, contract.endpoints[0])
        with zipfile.ZipFile(BytesIO(export_pytest_suite(plan))) as archive:
            source = archive.read("test_api_contract.py").decode()
            self.assertIn("requirements.txt", archive.namelist())
        # Only the pytest.skip interface is needed to exercise exported functions.
        fake_pytest = types.ModuleType("pytest")
        def skip(reason):
            raise unittest.SkipTest(reason)
        fake_pytest.skip = skip
        namespace = {}
        with patch.dict(sys.modules, {"pytest": fake_pytest}), patch.dict("os.environ", {"API_BASE_URL": "http://localhost:9876"}):
            exec(compile(source, "generated_test_api_contract.py", "exec"), namespace)
        return [value for name, value in namespace.items() if name.startswith("test_")]

    def test_export_sends_expected_request_and_checks_status(self):
        functions = self.load_export()
        with patch("requests.request", return_value=types.SimpleNamespace(status_code=201)) as transport:
            functions[0]()
            self.assertEqual(transport.call_args.args, ("POST", "http://localhost:9876/items"))
            self.assertEqual(transport.call_args.kwargs["json"], {"name": "sample_name"})
        with patch("requests.request", return_value=types.SimpleNamespace(status_code=500)):
            with self.assertRaises(AssertionError):
                functions[0]()

    def test_unconfirmed_case_skips_before_network_call(self):
        functions = self.load_export()
        with patch("requests.request") as transport:
            with self.assertRaises(unittest.SkipTest):
                functions[1]()
            transport.assert_not_called()


if __name__ == "__main__":
    unittest.main()
