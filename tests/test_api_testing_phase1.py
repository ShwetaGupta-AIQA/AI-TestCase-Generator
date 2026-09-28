import json
import unittest
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
