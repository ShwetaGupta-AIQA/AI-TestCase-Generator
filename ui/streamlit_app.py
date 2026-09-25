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
                           submit_document, submit_manual, demo_mode, generate_demo)
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


@st.fragment(run_every="2s")
def show_saved_run(run_id):
    try:
        cache_key = f"saved-run-{run_id}"
        saved = st.session_state.get(cache_key)
        if saved is None:
            saved = get_run(run_id)
            if saved["status"] in {"completed", "failed"}:
                if saved["status"] == "completed":
                    try:
                        saved["result"]["excel_data"] = download_excel(run_id)
                    except (BackendUnavailable, ValueError):
                        saved["result"]["excel_data"] = None
                st.session_state[cache_key] = saved
        st.info(f"Run {run_id[:8]} · {saved['stage']} ({saved['status']})")
        if saved["status"] == "completed":
            report = saved["result"]
            if "excel_data" not in report:
                try:
                    report["excel_data"] = download_excel(run_id)
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


def main():
    st.set_page_config(page_title="TestGen AI", page_icon="🧪", layout="wide")
    st.title("🧪 TestGen AI")
    st.subheader("AI-Powered Test Case Generator")
    st.write("Turn a requirement or document into QA scenarios, test cases and a traceable Excel workbook.")
    if demo_mode():
        demo_page()
        return
    with st.sidebar:
        st.header("About TestGen AI")
        st.write("Analyze requirements → Generate scenarios → Generate test cases → Validate → Export Excel")
        st.divider()
        st.caption("Document mode processes the first two extracted requirements. Text-based PDFs only; OCR is not included.")
        st.caption("Generation sends requirement text to the configured AI provider. Review generated results before use.")
        st.divider()
        st.subheader("Saved runs")
        try:
            history = get_history()
            for saved in history:
                label = saved.get("original_filename") or saved["run_id"][:8]
                if st.button(f"{label} · {saved['status']}", key=f"history-{saved['run_id']}"):
                    st.query_params["run_id"] = saved["run_id"]
                    st.rerun()
        except (BackendUnavailable, ValueError):
            st.caption("Start the API to load saved runs.")

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
            response = (submit_document(uploaded.name, content, pending[1]) if uploaded is not None
                        else submit_manual(text.strip(), pending[1]))
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
