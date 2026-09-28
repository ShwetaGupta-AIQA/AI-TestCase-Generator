import io
import json
import re
import zipfile
from xml.etree import ElementTree as ET

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from models.api_testing import ApiTestCase, ApiTestPlan


def _safe_name(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_").lower()
    return clean or "api_test"


def _url(plan: ApiTestPlan, case: ApiTestCase) -> str:
    return (plan.base_url.rstrip("/") + "/" + case.path.lstrip("/")) if plan.base_url else case.path


def export_api_plan_excel(plan: ApiTestPlan) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)
    specs = [
        ("Summary", ["Field", "Value"], [28, 80]),
        ("API Test Cases", ["Test Case ID", "Title", "Type", "Priority", "Method", "Path", "Expected Status", "Objective", "Steps", "Expected Result"], [16, 45, 20, 12, 10, 45, 18, 60, 80, 70]),
        ("Request Data", ["Test Case ID", "Headers", "Query Params", "Path Params", "Body"], [16, 60, 60, 60, 70]),
        ("Traceability", ["Endpoint", "Coverage Type", "Test Case ID", "Coverage Status"], [40, 24, 16, 18]),
    ]
    for name, headers, widths in specs:
        sheet = workbook.create_sheet(name)
        sheet.append(headers)
        for index, width in enumerate(widths, 1):
            sheet.column_dimensions[get_column_letter(index)].width = width

    summary = workbook["Summary"]
    endpoint = f"{plan.endpoint.method} {plan.endpoint.path}"
    for row in [
        ("Contract", plan.contract_title),
        ("Base URL", plan.base_url),
        ("Endpoint", endpoint),
        ("Generated Cases", len(plan.test_cases)),
        ("Coverage Summary", ", ".join(f"{name}: {count}" for name, count in plan.coverage_summary.items())),
        ("Retrieved Context", "\n".join(plan.retrieved_context)),
    ]:
        summary.append(row)

    for case in plan.test_cases:
        workbook["API Test Cases"].append([
            case.test_case_id, case.title, case.test_type, case.priority, case.method, case.path,
            case.expected_status, case.objective, "\n".join(f"{i}. {step}" for i, step in enumerate(case.steps, 1)),
            case.expected_result,
        ])
        workbook["Request Data"].append([
            case.test_case_id,
            json.dumps(case.request_headers, indent=2),
            json.dumps(case.query_params, indent=2),
            json.dumps(case.path_params, indent=2),
            json.dumps(case.request_body, indent=2),
        ])
        workbook["Traceability"].append([endpoint, case.test_type, case.test_case_id, "Covered"])

    for sheet in workbook:
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for row in sheet:
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = "s"
                cell.alignment = Alignment(vertical="top", wrap_text=True)
            sheet.row_dimensions[row[0].row].height = 36
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="203864")

    stream = io.BytesIO()
    workbook.save(stream)
    workbook.close()
    return stream.getvalue()


def export_postman_collection(plan: ApiTestPlan) -> bytes:
    collection = {
        "info": {
            "name": f"TestGen API Tests - {plan.endpoint.method} {plan.endpoint.path}",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": [],
    }
    for case in plan.test_cases:
        collection["item"].append({
            "name": f"{case.test_case_id} - {case.title}",
            "request": {
                "method": case.method,
                "header": [{"key": key, "value": value} for key, value in case.request_headers.items()],
                "url": {"raw": _url(plan, case), "query": [{"key": k, "value": v} for k, v in case.query_params.items()]},
                "body": {"mode": "raw", "raw": json.dumps(case.request_body, indent=2),
                         "options": {"raw": {"language": "json"}}} if case.request_body else None,
            },
            "event": [{"listen": "test", "script": {"type": "text/javascript", "exec": [
                f"pm.test('Expected status {case.expected_status}', function () {{",
                f"    pm.response.to.have.status({case.expected_status if case.expected_status.isdigit() else 200});",
                "});",
            ]}}],
        })
    return json.dumps(collection, indent=2).encode("utf-8")


def export_pytest_suite(plan: ApiTestPlan) -> bytes:
    lines = [
        "import os",
        "",
        "import requests",
        "",
        f"BASE_URL = os.getenv('API_BASE_URL', {plan.base_url!r}).rstrip('/')",
        "",
        "",
        "def _url(path):",
        "    return BASE_URL + '/' + path.lstrip('/') if BASE_URL else path",
        "",
    ]
    for case in plan.test_cases:
        lines.extend([
            f"def test_{_safe_name(case.test_case_id + '_' + case.title)}():",
            f"    response = requests.request({case.method!r}, _url({case.path!r}),",
            f"        headers={case.request_headers!r},",
            f"        params={case.query_params!r},",
            f"        json={case.request_body!r} if {bool(case.request_body)!r} else None, timeout=30)",
            f"    assert response.status_code == {int(case.expected_status) if case.expected_status.isdigit() else 200}",
            "",
        ])
    content = "\n".join(lines).encode("utf-8")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("test_api_contract.py", content)
        archive.writestr("README.md", "Run with: API_BASE_URL=https://test.example.com pytest test_api_contract.py\n")
    return stream.getvalue()


def export_soapui_project(plan: ApiTestPlan) -> bytes:
    project = ET.Element("con:soapui-project", {
        "xmlns:con": "http://eviware.com/soapui/config",
        "name": f"TestGen API Tests - {plan.contract_title}",
    })
    test_suite = ET.SubElement(project, "con:testSuite", {"name": f"{plan.endpoint.method} {plan.endpoint.path}"})
    for case in plan.test_cases:
        soap_case = ET.SubElement(test_suite, "con:testCase", {"name": f"{case.test_case_id} - {case.title}"})
        step = ET.SubElement(soap_case, "con:testStep", {"type": "restrequest", "name": case.test_case_id})
        config = ET.SubElement(step, "con:config", {"method": case.method})
        ET.SubElement(config, "con:endpoint").text = plan.base_url
        ET.SubElement(config, "con:resource").text = case.path
        ET.SubElement(config, "con:request").text = json.dumps({
            "headers": case.request_headers,
            "query": case.query_params,
            "body": case.request_body,
            "expectedStatus": case.expected_status,
        }, indent=2)
    ET.indent(project)
    return ET.tostring(project, encoding="utf-8", xml_declaration=True)
