import json
import yaml
import unittest
from unittest.mock import patch
import zipfile
from io import BytesIO
from xml.etree import ElementTree as ET

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from api.main import app
from models.api_testing import ApiManualRequest
from services.api_html_parser import parse_html_api_doc
from services.api_spec_parser import manual_contract, parse_openapi_spec
from services.api_test_designer import design_api_tests
from services.api_test_exporter import (export_api_plan_excel, export_postman_collection,
                                        export_pytest_suite, export_soapui_project)


OPENAPI_SPEC = json.dumps({
    "openapi": "3.0.0",
    "info": {"title": "Wallet API", "version": "1.0"},
    "servers": [{"url": "https://api.test.example.com"}],
    "paths": {
        "/registrations": {
            "post": {
                "summary": "Create registration",
                "parameters": [
                    {"name": "Request-Id", "in": "header", "required": True, "schema": {"type": "string"}},
                    {"name": "Partner-Id", "in": "header", "required": True, "schema": {"type": "string"}},
                ],
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["email", "cardName"],
                                "properties": {
                                    "email": {"type": "string", "format": "email"},
                                    "phone": {"type": "string"},
                                    "cardName": {"type": "string"},
                                },
                            }
                        }
                    }
                },
                "responses": {
                    "201": {"description": "Registration created"},
                    "400": {"description": "Invalid request"},
                    "503": {"description": "Retry later"},
                },
            }
        }
    },
})

HTML_DOC = """
<html>
<head><title>Add to Samsung Wallet API Guidelines</title></head>
<body>
<h1>Wallet API Guidelines</h1>
<h2>Get Card Data</h2>
<p>GET {Partner server URL}/cards/{cardId}/{refId}?fields={fields}</p>
<table>
<tr><td>Authorization</td><td>Required bearer token</td></tr>
<tr><td>x-request-id</td><td>Required request identifier</td></tr>
</table>
<p>Response status codes: 200, 400, 401, 404, 500, 503.</p>
<pre>{"cardId":"abc","status":"ACTIVE"}</pre>
<h2>Send Card State</h2>
<p>POST {Partner server URL}/cards/{cardId}/{refId}</p>
<pre>{"cardId":"abc","cardStatus":"SUSPENDED"}</pre>
<p>204, 400, 401, 500</p>
</body>
</html>
"""


class ApiTestingPhase1Tests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_openapi_parse_and_design(self):
        contract = parse_openapi_spec(OPENAPI_SPEC)
        self.assertEqual(contract.title, "Wallet API")
        endpoint = contract.endpoints[0]
        self.assertEqual(endpoint.method, "POST")
        self.assertEqual([header.name for header in endpoint.headers], ["Request-Id", "Partner-Id"])
        self.assertIn("email", [field.name for field in endpoint.body_fields])
        plan = design_api_tests(contract, endpoint)
        self.assertGreaterEqual(len(plan.test_cases), 8)
        self.assertEqual(plan.test_cases[0].expected_status, "201")
        self.assertIn("Negative", plan.coverage_summary)

    def test_yaml_matches_json_contract(self):
        yaml_text = yaml.safe_dump(json.loads(OPENAPI_SPEC), sort_keys=False)
        self.assertEqual(parse_openapi_spec(yaml_text), parse_openapi_spec(OPENAPI_SPEC))
        response = self.client.post("/api-testing/spec/parse", json={"spec_text": yaml_text})
        self.assertEqual(response.status_code, 200)

    def test_strategy_filters_exports_without_mutating_source(self):
        from services.api_test_strategy import select_test_scope
        contract = parse_openapi_spec(OPENAPI_SPEC)
        original = design_api_tests(contract, contract.endpoints[0])
        snapshot = original.model_dump()
        selected = select_test_scope(original, ["Functional"])
        self.assertEqual(len(selected.test_cases), 1)
        self.assertEqual(selected.coverage_summary, {"Functional": 1})
        collection = json.loads(export_postman_collection(selected))
        self.assertEqual(len(collection["item"]), 1)
        self.assertEqual(original.model_dump(), snapshot)
        empty = select_test_scope(original, ["Functional"], [selected.test_cases[0].test_case_id])
        self.assertEqual(empty.test_cases, [])
        self.assertEqual(empty.coverage_summary, {})

    def test_field_traceability_tracks_selected_scope(self):
        from services.api_coverage import field_design_coverage
        from services.api_test_strategy import select_test_scope
        contract = parse_openapi_spec(OPENAPI_SPEC)
        plan = design_api_tests(contract, contract.endpoints[0])
        rows = field_design_coverage(plan)
        email = next(row for row in rows if row["Field"] == "body:email")
        self.assertTrue(email["Selected test IDs"])
        self.assertEqual(email["Needs status confirmation"], 1)
        filtered = field_design_coverage(select_test_scope(plan, ["Functional"]))
        self.assertTrue(all(not row["Selected test IDs"] for row in filtered))

    def test_review_updates_export_and_preserves_requests(self):
        from services.api_test_strategy import review_test_cases
        contract = parse_openapi_spec(OPENAPI_SPEC)
        plan = design_api_tests(contract, contract.endpoints[0])
        case = plan.test_cases[0]
        reviewed = review_test_cases(plan, [{"test_case_id": case.test_case_id,
            "expected_status": "202", "priority": "Low", "expected_result": "Accepted for processing"}])
        self.assertEqual(case.expected_status, "201")
        self.assertEqual(reviewed.test_cases[0].request_body, case.request_body)
        collection = json.loads(export_postman_collection(reviewed))
        self.assertIn("to.have.status(202)", str(collection))
        for status in ["", "999", "200; malicious", "2XX"]:
            with self.assertRaises(ValueError):
                review_test_cases(plan, [{"test_case_id": case.test_case_id,
                    "expected_status": status, "priority": "Low", "expected_result": "Reviewed"}])

    def test_boundary_mutations_use_documented_constraints(self):
        spec = json.loads(OPENAPI_SPEC)
        schema = spec["paths"]["/registrations"]["post"]["requestBody"]["content"]["application/json"]["schema"]
        schema["properties"] = {"age": {"type": "integer", "minimum": 18, "maximum": 60},
                                "name": {"type": "string", "minLength": 2, "maxLength": 5},
                                "role": {"type": "string", "enum": ["USER", "ADMIN"]}}
        schema["required"] = ["age", "name", "role"]
        contract = parse_openapi_spec(json.dumps(spec))
        plan = design_api_tests(contract, contract.endpoints[0])
        boundaries = [case for case in plan.test_cases if case.test_type == "Boundary/Validation"]
        ages = [case.request_body["age"] for case in boundaries if case.title.startswith("age:")]
        self.assertEqual(ages, [17, 18, 19, 59, 60, 61])
        lengths = [len(case.request_body["name"]) for case in boundaries if case.title.startswith("name:")]
        self.assertEqual(lengths, [1, 2, 3, 4, 5, 6])
        self.assertTrue(any(case.request_body["role"] == "__outside_enum__" for case in boundaries))
        self.assertTrue(all(case.expected_status == "Needs confirmation" for case in boundaries))
        self.assertEqual(len({case.test_case_id for case in plan.test_cases}), len(plan.test_cases))

    def test_boundary_generation_is_bounded_and_skips_unknown_constraints(self):
        from services.api_boundaries import boundary_values
        self.assertEqual(boundary_values({"type": "string"}), [])
        self.assertEqual(boundary_values({"type": "string", "maxLength": 10000000}), [])
        self.assertEqual(boundary_values({"type": "string", "minLength": 2, "pattern": "^[0-9]+$"}), [])

    def test_url_import_returns_reviewed_source_snapshot(self):
        with patch("services.api_spec_fetcher.fetch_specification", return_value=OPENAPI_SPEC) as fetch:
            response = self.client.post("/api-testing/spec/parse", json={"url": "https://example.com/api.json"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source_text"], OPENAPI_SPEC)
        fetch.assert_called_once_with("https://example.com/api.json")

    def test_pasted_spec_takes_precedence_over_url(self):
        with patch("services.api_spec_fetcher.fetch_specification") as fetch:
            response = self.client.post("/api-testing/spec/parse", json={"spec_text": OPENAPI_SPEC, "url": "https://example.com/api.json"})
        self.assertEqual(response.status_code, 200)
        fetch.assert_not_called()

    def test_spec_url_rejects_local_addresses_and_credentials(self):
        from services.api_spec_fetcher import fetch_specification
        with self.assertRaisesRegex(ValueError, "without credentials"):
            fetch_specification("https://user:password@example.com/spec")
        with patch("services.api_spec_fetcher.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]):
            with self.assertRaisesRegex(ValueError, "Private or local"):
                fetch_specification("https://localhost/spec")

    def test_invalid_yaml_and_aliases_report_actionable_errors(self):
        response = self.client.post("/api-testing/spec/parse", json={"spec_text": "openapi: [broken"})
        self.assertEqual(response.status_code, 422)
        self.assertIn("line", response.json()["detail"])
        with self.assertRaisesRegex(ValueError, "line"):
            parse_openapi_spec("openapi: [broken")
        with self.assertRaisesRegex(ValueError, "anchors and aliases"):
            parse_openapi_spec("root: &root\n  nested: *root")

    def test_preserves_nested_types_constraints_and_security(self):
        spec = json.loads(OPENAPI_SPEC)
        operation = spec["paths"]["/registrations"]["post"]
        operation["security"] = [{"bearer": []}]
        schema = {"type": "object", "properties": {
            "age": {"type": "integer", "minimum": 18},
            "active": {"type": "boolean"},
            "profile": {"type": "object", "properties": {"count": {"type": "integer"}}},
        }}
        operation["requestBody"]["content"]["application/json"]["schema"] = schema
        contract = parse_openapi_spec(json.dumps(spec))
        endpoint = contract.endpoints[0]
        self.assertEqual(endpoint.request_schema, schema)
        self.assertEqual(endpoint.security, [{"bearer": []}])
        body = design_api_tests(contract, endpoint).test_cases[0].request_body
        self.assertEqual(body["age"], 18)
        self.assertIs(body["active"], True)
        self.assertIsInstance(body["profile"]["count"], int)

    def test_html_does_not_invent_status_or_execution_url(self):
        contract = parse_html_api_doc("GET /items\nNo response documented", "https://docs.example.com/guide")
        self.assertEqual(contract.base_url, "")
        self.assertEqual(contract.endpoints[0].responses, [])
        plan = design_api_tests(contract, contract.endpoints[0])
        self.assertEqual(plan.test_cases[0].expected_status, "Needs confirmation")
        collection = json.loads(export_postman_collection(plan))
        self.assertNotIn("to.have.status(200)", json.dumps(collection))
        with zipfile.ZipFile(BytesIO(export_pytest_suite(plan))) as archive:
            self.assertIn("pytest.skip", archive.read("test_api_contract.py").decode())

    def test_reviewed_contract_drives_generation(self):
        parsed = self.client.post("/api-testing/spec/parse", json={"spec_text": OPENAPI_SPEC}).json()
        reviewed = parsed["endpoints"][0]["contract"]
        reviewed["responses"] = [{"status_code": "202", "description": "User confirmed"}]
        response = self.client.post("/api-testing/design/spec", json={
            "spec_text": OPENAPI_SPEC, "reviewed_endpoint": reviewed})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["plan"]["test_cases"][0]["expected_status"], "202")

    def test_rejects_unsupported_version_and_missing_reference(self):
        with self.assertRaisesRegex(ValueError, "Supported versions"):
            parse_openapi_spec('{"swagger":"2.0", "paths":{}}')
        spec = json.loads(OPENAPI_SPEC)
        spec["paths"]["/registrations"]["post"]["requestBody"] = {"$ref": "#/missing"}
        with self.assertRaisesRegex(ValueError, "Unresolved"):
            parse_openapi_spec(json.dumps(spec))

    def test_manual_request_generates_senior_api_coverage(self):
        contract = manual_contract(ApiManualRequest(
            title="Registration API",
            base_url="https://api.test.example.com",
            method="POST",
            path="/registrations",
            required_headers=["Request-Id", "Partner-Id"],
            required_body_fields=["email", "cardName"],
            success_status="201",
            error_statuses=["400", "500", "503"],
        ))
        plan = design_api_tests(contract, contract.endpoints[0])
        titles = [case.title for case in plan.test_cases]
        self.assertIn("Repeat request handles duplicate/idempotency behavior", titles)
        self.assertTrue(any("Correlation identifier" in title for title in titles))

    def test_html_doc_parse_and_design(self):
        contract = parse_html_api_doc(HTML_DOC, "https://developer.samsung.com/wallet/addtosamsungwallet/apiguidelines.html")
        self.assertEqual(contract.source_type, "html")
        self.assertEqual(len(contract.endpoints), 2)
        endpoint = contract.endpoints[0]
        self.assertEqual(endpoint.method, "GET")
        self.assertEqual(endpoint.path, "/cards/{cardId}/{refId}")
        self.assertIn("cardId", [param.name for param in endpoint.path_params])
        self.assertIn("fields", [param.name for param in endpoint.query_params])
        self.assertIn("Authorization", [header.name for header in endpoint.headers])
        plan = design_api_tests(contract, endpoint)
        self.assertGreaterEqual(plan.coverage_summary["Negative"], 1)
        self.assertTrue(any("Selected endpoint: GET /cards/{cardId}/{refId}" == item for item in plan.retrieved_context))

    def test_fastapi_phase1_endpoints_and_exports(self):
        parsed = self.client.post("/api-testing/spec/parse", json={"spec_text": OPENAPI_SPEC})
        self.assertEqual(parsed.status_code, 200)
        endpoint_key = parsed.json()["endpoints"][0]["key"]
        designed = self.client.post("/api-testing/design/spec",
                                    json={"spec_text": OPENAPI_SPEC, "endpoint_key": endpoint_key})
        self.assertEqual(designed.status_code, 200)
        plan = designed.json()["plan"]

        excel = self.client.post("/api-testing/export/excel", json={"plan": plan})
        self.assertEqual(excel.status_code, 200)
        workbook = load_workbook(BytesIO(excel.content))
        self.assertEqual(workbook["Summary"]["B2"].value, "Wallet API")
        workbook.close()

        postman = self.client.post("/api-testing/export/postman", json={"plan": plan})
        self.assertEqual(json.loads(postman.content)["info"]["schema"].split("/")[-1], "collection.json")

        pytest_zip = self.client.post("/api-testing/export/pytest", json={"plan": plan})
        with zipfile.ZipFile(BytesIO(pytest_zip.content)) as archive:
            self.assertIn("test_api_contract.py", archive.namelist())

        soapui = self.client.post("/api-testing/export/soapui", json={"plan": plan})
        self.assertIn(b"soapui-project", soapui.content)
        xml = ET.fromstring(soapui.content)
        namespace = {"con": "http://eviware.com/soapui/config"}
        self.assertIsNotNone(xml.find("con:wssContainer", namespace))
        self.assertIsNotNone(xml.find("con:interface", namespace))
        self.assertIsNotNone(xml.find("con:testSuite", namespace))

    def test_fastapi_html_endpoints(self):
        parsed = self.client.post("/api-testing/html/parse", json={"html_text": HTML_DOC})
        self.assertEqual(parsed.status_code, 200)
        endpoint_key = parsed.json()["endpoints"][1]["key"]
        designed = self.client.post("/api-testing/design/html",
                                    json={"html_text": HTML_DOC, "endpoint_key": endpoint_key})
        self.assertEqual(designed.status_code, 200)
        plan = designed.json()["plan"]
        self.assertEqual(plan["endpoint"]["method"], "POST")
        self.assertEqual(plan["endpoint"]["path"], "/cards/{cardId}/{refId}")


if __name__ == "__main__":
    unittest.main()
