"""Launch from the project root: python -m streamlit run ui/streamlit_app.py"""
from pathlib import Path
import hashlib
import sys
import logging
from uuid import uuid4

# Streamlit executes this file as a script; make the project package root explicit.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
from services.generation_errors import generation_error_message
from openai import APIError
from services.provider_errors import provider_error_message
from ui.api_client import (BackendUnavailable, download_excel, get_history, get_run,
                           submit_document, submit_manual, demo_mode, generate_demo, create_workspace,
                           workspace_required, parse_api_spec, design_manual_api_tests,
                           design_spec_api_tests, parse_api_html, design_html_api_tests,
                           export_api_tests)
from services.demo_limits import MAX_UPLOAD_BYTES, MAX_TEXT_CHARS
from evaluation.evaluator import evaluate_test_suite
from models.test_case import TestCase
from models.test_scenario import TestScenario


def show_results(report):
    results = report["results"]
    scenarios = [s for result in results for s in result["scenarios"]]
    cases = [c for result in results for c in result["test_cases"]]
    rejected = [c for result in results for c in result["rejected_test_cases"]]
    st.success(f"Processed {report['processed_count']} of {report['extracted_count']} requirements.")
    evaluation = evaluate_test_suite(
        [TestCase.model_validate(c) for c in cases + rejected],
        [TestScenario.model_validate(s) for s in scenarios])
    for column, label, count in zip(st.columns(5),
            ["Requirements", "Test Cases", "Completeness", "Traceability", "Duplicate Rate"],
            [len(results), evaluation.total_test_cases, f"{evaluation.completeness_score}%",
             f"{evaluation.traceability_score}%", f"{evaluation.duplicate_rate}%"]):
        column.metric(label, count)
    st.caption(f"{len(scenarios)} scenarios · {len(cases)} accepted cases. Quality metrics include rejected cases; traceability measures application-assigned mappings.")
    for issue in evaluation.issues:
        st.warning(issue)
    if not evaluation.issues:
        st.success("No basic quality issues detected.")
    if rejected:
        st.warning(f"{len(rejected)} test cases failed QA validation and are excluded from the Excel export.")
    requirement_tab, scenario_tab, case_tab = st.tabs(["Requirements", "Scenarios", "Test Cases"])
    with requirement_tab:
        for result in results:
            analysis = result["analysis"]
            with st.expander(f"{result['source_id']} → {analysis['requirement_id']}"):
                st.write("**Requirement:**", result["requirement"])
                for key in ["actor", "functionality", "business_rules", "constraints", "missing_information", "assumptions", "clarification_questions"]:
                    st.write(f"**{key.replace('_', ' ').title()}:**", analysis[key])
                if result["boundary_analysis"]:
                    st.write("**Boundary analysis:**", result["boundary_analysis"])
    with scenario_tab:
        for scenario in scenarios:
            with st.expander(f"{scenario['scenario_id']} — {scenario['title']}"):
                st.write("**Requirement:**", scenario["requirement_id"])
                st.write("**Type:**", scenario["scenario_type"])
                st.write("**Description:**", scenario["description"])
    with case_tab:
        for case in cases:
            with st.expander(f"{case['test_case_id']} — {case['title']}"):
                for key in ["requirement_id", "scenario_id", "test_type", "priority", "preconditions"]:
                    st.write(f"**{key.replace('_', ' ').title()}:**", case[key])
                st.write("**Steps:**")
                for number, step in enumerate(case["steps"], 1):
                    st.write(f"{number}. {step}")
                st.write("**Test Data:**", case["test_data"])
                st.write("**Expected Result:**", case["expected_result"])
        with st.expander("QA validation details"):
            for result in results:
                st.write(result["validation_summary"])
                for validation in result["validation_results"]:
                    for error in validation["errors"]:
                        st.error(f"{validation['test_case_id']}: {error}")
                    for warning in validation["warnings"]:
                        st.warning(f"{validation['test_case_id']}: {warning}")
                if result["rejected_test_cases"]:
                    st.write("Rejected cases", result["rejected_test_cases"])
    if report.get("excel_data"):
        st.download_button("Download Test Cases Excel", report["excel_data"],
                           file_name="TestGen_Output.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def workspace_token():
    """Keep the opaque Stage 2 token in the current Streamlit session only."""
    if not workspace_required():
        return None
    if "workspace_token" not in st.session_state:
        st.session_state["workspace_token"] = create_workspace()
    return st.session_state["workspace_token"]


@st.fragment(run_every="2s")
def show_saved_run(run_id):
    try:
        cache_key = f"saved-run-{run_id}"
        saved = st.session_state.get(cache_key)
        if saved is None:
            saved = get_run(run_id, workspace_token())
            if saved["status"] in {"completed", "failed"}:
                if saved["status"] == "completed":
                    try:
                        saved["result"]["excel_data"] = download_excel(run_id, workspace_token())
                    except (BackendUnavailable, ValueError):
                        saved["result"]["excel_data"] = None
                st.session_state[cache_key] = saved
        st.info(f"Run {run_id[:8]} · {saved['stage']} ({saved['status']})")
        if saved["status"] == "completed":
            report = saved["result"]
            if "excel_data" not in report:
                try:
                    report["excel_data"] = download_excel(run_id, workspace_token())
                except (BackendUnavailable, ValueError):
                    report["excel_data"] = None
            if not report.get("excel_data"):
                st.warning("Saved results are available, but the Excel workbook is missing.")
            show_results(report)
        elif saved["status"] == "failed":
            st.error(saved.get("error") or "Generation failed.")
        else:
            st.caption("This job continues in the worker if you close or refresh this page.")
    except (BackendUnavailable, ValueError) as exc:
        st.error(str(exc))


def demo_page():
    st.caption("Public demo: session-only results. Refreshing or restarting may clear your results. Download Excel before leaving.")
    st.caption("Up to two document requirements, three scenarios per requirement and three cases per scenario. Use sample or nonconfidential requirements; text is sent to the AI provider.")
    mode = st.radio("Choose input method", ["Enter Requirement", "Upload Document"], horizontal=True)
    filename, content, text = None, None, ""
    if mode == "Enter Requirement":
        if st.button("Load Sample Requirement"):
            st.session_state["demo_requirement"] = "The password must contain between 8 and 20 characters. Reject passwords outside this range."
        text = st.text_area("Enter User Story / Requirement", key="demo_requirement",
                            height=150, max_chars=MAX_TEXT_CHARS)
        ready = 5 <= len(text.strip()) <= MAX_TEXT_CHARS
        fingerprint = (mode, text)
    else:
        uploaded = st.file_uploader("Upload TXT, DOCX or text-based PDF (up to 4 MB)", type=["txt", "docx", "pdf"])
        if uploaded is not None:
            filename, content = uploaded.name, uploaded.getvalue()
        ready = content is not None and 0 < len(content) <= MAX_UPLOAD_BYTES
        if uploaded is not None and not ready:
            st.error("Choose a nonempty document no larger than 4 MB.")
        fingerprint = (mode, filename, hashlib.sha256(content or b"").hexdigest())
    if st.session_state.get("demo_input") != fingerprint:
        st.session_state.pop("demo_result", None)
        st.session_state["demo_input"] = fingerprint
    if st.button("Analyze & Generate Test Cases", type="primary", disabled=not ready):
        st.session_state.pop("demo_result", None)
        try:
            with st.spinner("Generating and validating tests. Keep this page open; this can take several minutes."):
                st.session_state["demo_result"] = generate_demo(
                    requirement=text.strip(), filename=filename, content=content)
        except (BackendUnavailable, ValueError) as exc:
            st.error(generation_error_message(exc))
    if st.session_state.get("demo_result"):
        show_results(st.session_state["demo_result"])


def _split_names(value):
    return [item.strip() for item in value.replace("\n", ",").split(",") if item.strip()]


def _show_api_plan(plan):
    from models.api_testing import ApiTestPlan
    from services.api_test_strategy import STRATEGIES, select_test_scope, review_test_cases
    import json
    source_plan = ApiTestPlan.model_validate(plan)
    scope_key = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()[:16]
    st.subheader("Review test expectations")
    st.caption("Confirm expectations from your API contract. These edits apply to the selected cases and all exports in this session.")
    fields = ["test_case_id", "title", "expected_status", "priority", "expected_result"]
    rows = [{field: getattr(case, field) for field in fields} for case in source_plan.test_cases]
    reviewed_rows = st.data_editor(rows, disabled=["test_case_id", "title"],
                                   column_config={"priority": st.column_config.SelectboxColumn(options=["High", "Medium", "Low"], required=True)},
                                   key="test-review-" + scope_key, hide_index=True)
    try:
        source_plan = review_test_cases(source_plan, reviewed_rows)
    except ValueError as exc:
        st.error(str(exc))
        return
    st.subheader("Test strategy and review scope")
    preset = st.radio("Coverage preset", list(STRATEGIES), index=1, horizontal=True, key="preset-" + scope_key)
    available = list(dict.fromkeys(case.test_type for case in source_plan.test_cases))
    categories = st.multiselect("Include test categories", available,
                                default=[name for name in STRATEGIES[preset] if name in available],
                                key="categories-" + scope_key + preset)
    st.caption("Presets select existing designs. Advanced adds applicable idempotency and observability designs; "
               "it does not add security or performance execution.")
    scoped = select_test_scope(source_plan, categories)
    labels = {case.test_case_id: case.title for case in scoped.test_cases}
    excluded = st.multiselect("Exclude individual cases from review and export", list(labels),
                              format_func=lambda case_id: f"{case_id} - {labels[case_id]}",
                              key="exclude-" + scope_key + preset + ",".join(categories))
    plan = select_test_scope(source_plan, categories, excluded).model_dump()
    if not plan["test_cases"]:
        st.info("Select at least one test case to review or export.")
        return
    pending = sum(not case["expected_status"].isdigit() for case in plan["test_cases"])
    from services.api_coverage import field_design_coverage
    coverage_rows = field_design_coverage(ApiTestPlan.model_validate(plan))
    with st.expander("Field traceability and design gaps", expanded=True):
        if coverage_rows:
            covered = sum(bool(row["Selected test IDs"]) for row in coverage_rows)
            st.write(f"{covered} of {len(coverage_rows)} documented top-level fields have a selected field-specific test design.")
            st.dataframe(coverage_rows, hide_index=True)
        else:
            st.info("No structured fields were extracted. Review the contract before assessing field coverage.")
        st.caption("A linked test does not mean every constraint is covered. This panel excludes nested fields and does not report execution results.")
        st.write("Review gaps: nested/composed constraints, authentication and ownership scenarios, business rules, and error-trigger setup.")
    st.write(f"Selected {len(plan['test_cases'])} of {len(source_plan.test_cases)} generated designs; "
             f"{pending} need expected-status confirmation.")
    endpoint = plan["endpoint"]
    st.success(f"Generated {len(plan['test_cases'])} API test cases for {endpoint['method']} {endpoint['path']}.")
    st.caption("Boundary generation currently covers top-level body/query integer limits, string lengths and enums. "
               "Nested, decimal, pattern and composed constraints need manual review. Counts show designed tests, not executed coverage.")
    for column, (label, value) in zip(st.columns(4), [
        ("Functional", plan["coverage_summary"].get("Functional", 0)),
        ("Negative", plan["coverage_summary"].get("Negative", 0)),
        ("Validation", plan["coverage_summary"].get("Boundary/Validation", 0)),
        ("Error Handling", plan["coverage_summary"].get("Error Handling", 0)),
    ]):
        column.metric(label, value)
    with st.expander("Retrieved API context"):
        for item in plan.get("retrieved_context", []):
            st.write(item)
    case_tab, export_tab = st.tabs(["API Test Cases", "Exports"])
    with case_tab:
        for case in plan["test_cases"]:
            with st.expander(f"{case['test_case_id']} - {case['title']}"):
                st.write("**Type:**", case["test_type"])
                st.write("**Priority:**", case["priority"])
                st.write("**Expected Status:**", case["expected_status"])
                st.write("**Objective:**", case["objective"])
                st.write("**Headers:**", case["request_headers"])
                st.write("**Query Params:**", case["query_params"])
                st.write("**Request Body:**", case["request_body"])
                st.write("**Expected Result:**", case["expected_result"])
    with export_tab:
        st.caption("Choose the output your reviewer or team wants to inspect or run locally.")
        st.info("Pytest and SoapUI 5.10.0 runners have been checked against a local mock API. "
                "SoapUI checks cover JSON, headers, query/path parameters and status assertions. "
                "Postman CLI checks cover JSON, headers, encoded queries, status assertions and skipping unconfirmed cases. "
                "Postman and SoapUI desktop imports remain unverified.")
        for label, export_format, filename, mime in [
            ("Download Excel", "excel", "TestGen_API_Tests.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("Download Postman Collection", "postman", "TestGen_Postman_Collection.json", "application/json"),
            ("Download Pytest Suite", "pytest", "TestGen_Pytest_Suite.zip", "application/zip"),
            ("Download SoapUI Project (experimental)", "soapui", "TestGen_SoapUI_Project.xml", "application/xml"),
        ]:
            try:
                data = export_api_tests(plan, export_format)
                st.download_button(label, data, file_name=filename, mime=mime, key=f"api-export-{export_format}")
            except (BackendUnavailable, ValueError) as exc:
                st.error(f"{label} failed: {exc}")


def _review_api_endpoint(choice):
    import json
    contract = choice.get("contract")
    if not contract:
        st.warning("Deploy the updated backend to enable contract review.")
        return None
    for warning in contract.get("warnings", []):
        st.warning(warning)
    st.caption("Review extracted details before generation. Use advanced JSON for nested schemas and authentication.")
    st.write("Source:", contract.get("source_reference", ""))
    review_key = "review-" + str(hash(json.dumps(contract, sort_keys=True)))
    mode = st.radio("Contract editor", ["Guided fields", "Advanced JSON"], key=review_key)
    if mode == "Guided fields":
        import copy
        value = copy.deepcopy(contract)
        methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
        value["method"] = st.selectbox("HTTP method", methods, index=methods.index(contract["method"]), key=review_key + "method")
        value["path"] = st.text_input("Endpoint path", contract["path"], key=review_key + "path")
        value["summary"] = st.text_input("Purpose", contract.get("summary", ""), key=review_key + "summary")
        value["description"] = st.text_area("Rules and source excerpt", contract.get("description", ""), key=review_key + "description")
        response_rows = [{"status_code": item["status_code"], "description": item.get("description", "")}
                         for item in contract.get("responses", [])]
        import pandas as pd
        rows = st.data_editor(pd.DataFrame(response_rows, columns=["status_code", "description"]),
                              num_rows="dynamic", key=review_key + "responses")
        originals = {item["status_code"]: item for item in contract.get("responses", [])}
        value["responses"] = []
        for row in rows.to_dict("records"):
            code = str(row.get("status_code") or "").strip()
            if not code:
                continue
            if not (code == "default" or len(code) == 3 and code[0] in "12345" and (code.isdigit() or code[1:] == "XX")):
                st.error("Response codes must be HTTP codes, ranges such as 2XX, or default.")
                return None
            value["responses"].append({**originals.get(code, {}), "status_code": code,
                                       "description": str(row.get("description") or "")})
        with st.expander("Parameters, schemas and authentication"):
            st.json({name: contract.get(name, {}) for name in ["headers", "query_params", "path_params", "body_fields", "request_schema", "security"]})
        if not value["path"].startswith("/"):
            st.error("Endpoint path must start with /.")
            return None
        st.caption("Switching editors uses the original imported contract. Generate from the current editor to apply corrections.")
        return value
    edited = st.text_area("Endpoint contract", json.dumps(contract, indent=2), height=300,
                          key="contract-review-" + str(hash(json.dumps(contract, sort_keys=True))))
    try:
        value = json.loads(edited)
        if not isinstance(value, dict):
            raise ValueError("Contract must be a JSON object.")
        return value
    except ValueError as exc:
        st.error(str(exc))
        return None


def api_testing_page():
    st.subheader("API Testing - Phase 1")
    st.write("Design API tests from endpoint details, OpenAPI JSON/YAML, or HTML documentation.")
    source = st.radio("API input method", ["Paste API Details", "Import OpenAPI", "Import HTML / URL"], horizontal=True)
    if source == "Paste API Details":
        with st.form("manual-api-form"):
            left, right = st.columns(2)
            title = left.text_input("API / Service Name", value="Manual API")
            base_url = right.text_input("Base URL", placeholder="https://api.test.example.com")
            method = left.selectbox("Method", ["GET", "POST", "PUT", "PATCH", "DELETE"])
            path = right.text_input("Path", value="/registrations")
            summary = st.text_input("Business Purpose", placeholder="Create a registration for a wallet/account flow")
            description = st.text_area("Rules / Notes", height=90,
                                       placeholder="Paste validation rules, auth notes, response behavior or business constraints.")
            required_headers = st.text_input("Required Headers", placeholder="Request-Id, Partner-Id, Authorization")
            required_query = st.text_input("Required Query Params", placeholder="countryCode, locale")
            required_body = st.text_input("Required Body Fields", placeholder="email, phone, cardName")
            optional_body = st.text_input("Optional Body Fields", placeholder="marketingOptIn, referenceId")
            success_status = st.text_input("Success Status", value="201")
            error_statuses = st.text_input("Error Statuses", value="400, 401, 409, 500, 503")
            submitted = st.form_submit_button("Generate API Test Plan", type="primary")
        if submitted:
            payload = {
                "title": title,
                "base_url": base_url,
                "method": method,
                "path": path,
                "summary": summary,
                "description": description,
                "required_headers": _split_names(required_headers),
                "required_query_params": _split_names(required_query),
                "required_body_fields": _split_names(required_body),
                "optional_body_fields": _split_names(optional_body),
                "success_status": success_status,
                "error_statuses": _split_names(error_statuses),
            }
            try:
                st.session_state["api_test_plan"] = design_manual_api_tests(payload)
            except (BackendUnavailable, ValueError) as exc:
                st.error(str(exc))
    elif source == "Import OpenAPI":
        st.caption("Supported: OpenAPI 3.0 / 3.1, JSON or YAML. Bundle external references before importing.")
        uploaded = st.file_uploader("OpenAPI specification", type=["json", "yaml", "yml"])
        spec_url = st.text_input("Or import a public HTTPS specification URL", placeholder="https://example.com/openapi.yaml")
        spec_text = st.text_area("Or paste OpenAPI JSON / YAML", value=(uploaded.getvalue().decode("utf-8-sig", errors="replace") if uploaded else ""),
                                 height=220)
        st.caption("Uploaded or pasted content takes precedence over the URL. URL imports use the final URL without redirects.")
        if st.button("Read API Specification", disabled=not spec_text.strip() and not spec_url.strip()):
            try:
                parsed = parse_api_spec(spec_text, spec_url.strip())
                st.session_state["api_spec_text"] = parsed.get("source_text") or spec_text
                st.session_state["api_spec_endpoints"] = parsed["endpoints"]
            except (BackendUnavailable, ValueError) as exc:
                st.session_state.pop("api_spec_endpoints", None)
                st.error(str(exc))
        endpoints = st.session_state.get("api_spec_endpoints", [])
        if endpoints:
            search = st.text_input("Search endpoints by method, path or description", key="spec-search")
            endpoints = [item for item in endpoints if search.lower() in item["label"].lower()]
            if not endpoints:
                st.info("No endpoints match your search.")
        if endpoints:
            labels = [endpoint["label"] for endpoint in endpoints]
            selected_label = st.selectbox("Which API do you want to test?", labels)
            endpoint_key = endpoints[labels.index(selected_label)]["key"]
            reviewed = _review_api_endpoint(endpoints[labels.index(selected_label)])
            if st.button("Generate API Test Plan", type="primary", disabled=reviewed is None):
                try:
                    st.session_state["api_test_plan"] = design_spec_api_tests(st.session_state["api_spec_text"], endpoint_key, reviewed)
                except (BackendUnavailable, ValueError) as exc:
                    st.error(str(exc))
    else:
        doc_url = st.text_input("API documentation URL", placeholder="https://developer.example.com/api-guidelines.html")
        html_upload = st.file_uploader("Or upload HTML documentation", type=["html", "htm", "txt"])
        html_text = st.text_area("Or paste copied HTML / documentation text", height=220,
                                 value=html_upload.getvalue().decode("utf-8", errors="replace") if html_upload else "",
                                 placeholder="Paste the API method, path, headers, payload and status-code sections.")
        if st.button("Read HTML API Documentation", disabled=not doc_url.strip() and len(html_text.strip()) < 20):
            try:
                parsed = parse_api_html(html_text=html_text.strip(), url=doc_url.strip())
                st.session_state["api_html_text"] = html_text.strip()
                st.session_state["api_html_url"] = doc_url.strip()
                st.session_state["api_html_endpoints"] = parsed["endpoints"]
            except (BackendUnavailable, ValueError) as exc:
                st.error(str(exc))
        endpoints = st.session_state.get("api_html_endpoints", [])
        if endpoints:
            search = st.text_input("Search extracted endpoints", key="html-search")
            endpoints = [item for item in endpoints if search.lower() in item["label"].lower()]
            if not endpoints:
                st.info("No endpoints match your search.")
        if endpoints:
            labels = [endpoint["label"] for endpoint in endpoints]
            selected_label = st.selectbox("Confirm extracted API to test", labels)
            endpoint_key = endpoints[labels.index(selected_label)]["key"]
            reviewed = _review_api_endpoint(endpoints[labels.index(selected_label)])
            if st.button("Generate API Test Plan", type="primary", disabled=reviewed is None):
                try:
                    st.session_state["api_test_plan"] = design_html_api_tests(
                        html_text=st.session_state.get("api_html_text", ""),
                        url=st.session_state.get("api_html_url", ""),
                        endpoint_key=endpoint_key, reviewed_endpoint=reviewed)
                except (BackendUnavailable, ValueError) as exc:
                    st.error(str(exc))
    if st.session_state.get("api_test_plan"):
        _show_api_plan(st.session_state["api_test_plan"])


def main():
    st.set_page_config(page_title="TestGen AI", page_icon="🧪", layout="wide")
    st.title("🧪 TestGen AI")
    st.subheader("AI-Powered Test Case Generator")
    st.write("Turn a requirement or document into QA scenarios, test cases and a traceable Excel workbook.")
    with st.sidebar:
        st.header("About TestGen AI")
        workspace_mode = st.selectbox("Workspace", ["Requirement Generator", "API Testing - Phase 1"], key="workspace-mode")
        st.write("Analyze requirements â†’ Generate scenarios â†’ Generate test cases â†’ Validate â†’ Export Excel")
    if workspace_mode == "API Testing - Phase 1":
        api_testing_page()
        return
    if demo_mode():
        demo_page()
        return
    with st.sidebar:
        st.header("About TestGen AI")
        workspace_mode = st.selectbox("Workspace", ["Requirement Generator", "API Testing - Phase 1"], key="workspace-mode-durable")
        st.write("Analyze requirements → Generate scenarios → Generate test cases → Validate → Export Excel")
        st.divider()
        st.caption("Document mode processes the first two extracted requirements. Text-based PDFs only; OCR is not included.")
        st.caption("Generation sends requirement text to the configured AI provider. Review generated results before use.")
        st.divider()
        st.subheader("Saved runs")
        try:
            history = get_history(workspace_token())
            for saved in history:
                label = saved.get("original_filename") or saved["run_id"][:8]
                if st.button(f"{label} · {saved['status']}", key=f"history-{saved['run_id']}"):
                    st.query_params["run_id"] = saved["run_id"]
                    st.rerun()
        except (BackendUnavailable, ValueError):
            st.caption("Start the API to load saved runs.")

    if workspace_mode == "API Testing - Phase 1":
        api_testing_page()
        return

    active_run_id = st.query_params.get("run_id")
    if active_run_id:
        if st.button("New run"):
            st.query_params.clear()
            st.rerun()
        show_saved_run(active_run_id)
        return
    mode = st.radio("Choose input method", ["Upload Document", "Enter Requirement"], horizontal=True)
    uploaded, text, content = None, "", b""
    if mode == "Upload Document":
        uploaded = st.file_uploader("Upload BRD / Requirements Document", type=["txt", "docx", "pdf"])
        if uploaded is not None:
            content = uploaded.getvalue()
            st.success(f"File selected: {uploaded.name}")
        fingerprint = (mode, uploaded.name if uploaded else "", hashlib.sha256(content).hexdigest())
        ready = uploaded is not None and 0 < len(content) <= 10 * 1024 * 1024
        if uploaded is not None and not ready:
            st.error("Choose a nonempty document no larger than 10 MiB.")
    else:
        text = st.text_area("Enter User Story / Requirement", height=150,
                            placeholder="The password must contain between 8 and 20 characters.")
        fingerprint = (mode, text)
        ready = len(text.strip()) >= 5
        if text and not ready:
            st.info("Enter at least five non-whitespace characters.")
    if st.session_state.get("input_fingerprint") != fingerprint:
        st.session_state.pop("generation_result", None)
        st.session_state["input_fingerprint"] = fingerprint
    if st.button("Analyze & Generate Test Cases", type="primary", disabled=not ready):
        try:
            fingerprint_bytes = ((mode + "\0" + (uploaded.name if uploaded else "") + "\0").encode()
                                 + (content if uploaded is not None else text.strip().encode()))
            request_fingerprint = hashlib.sha256(fingerprint_bytes).hexdigest()
            pending = st.session_state.get("pending_submission")
            if not pending or pending[0] != request_fingerprint:
                pending = (request_fingerprint, str(uuid4()))
                st.session_state["pending_submission"] = pending
            token = workspace_token()
            response = (submit_document(uploaded.name, content, pending[1], token) if uploaded is not None
                        else submit_manual(text.strip(), pending[1], token))
            st.session_state.pop("pending_submission", None)
            st.query_params["run_id"] = response["run_id"]
            st.rerun()
        except APIError as exc:
            st.error(provider_error_message(exc))
        except (BackendUnavailable, ValueError, OSError) as exc:
            detail = generation_error_message(exc)
            logging.getLogger("testgen").error("Generation failed: %s", detail)
            st.error(f"Generation failed: {detail}")


if __name__ == "__main__":
    main()
