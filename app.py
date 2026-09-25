"""Interactive and command-line test generation."""
import argparse
import contextvars
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys

from openai import APIError
from models.test_case import TestCase
from qa_engine.boundary_analyzer import generate_boundary_values
from qa_engine.test_case_validator import validate_test_case, find_duplicate_titles
from utils.id_generator import IDGenerator
from evaluation.evaluator import evaluate_test_suite
from services.document_reader import read_document
from services.requirement_extractor import extract_requirements
from services.requirement_analyzer import analyze_requirement
from services.scenario_generator import generate_scenarios
from services.test_case_generator import generate_test_cases
from services import demo_limits


def run_pipeline(requirement, id_generator=None):
    if id_generator is None:
        id_generator = IDGenerator()
    print("[1/3] Analyzing requirement...", file=sys.stderr)
    analysis = analyze_requirement(requirement)
    analysis.requirement_id = id_generator.next_requirement_id()
    boundary_analysis = []
    print("\n===== BOUNDARY ANALYSIS =====", file=sys.stderr)
    for constraint in analysis.boundary_constraints:
        values = []
        if constraint.minimum is not None and constraint.maximum is not None:
            values = generate_boundary_values(constraint.minimum, constraint.maximum)
        boundary_analysis.append({**constraint.model_dump(), "boundary_values": values})
        print(f"Field: {constraint.field}\nMinimum: {constraint.minimum}\n"
              f"Maximum: {constraint.maximum}\nUnit: {constraint.unit}", file=sys.stderr)
        for boundary in values:
            print(f"{boundary['value']} -> {boundary['boundary_type']} -> "
                  f"Valid: {boundary['expected_valid']}", file=sys.stderr)
        if not values:
            print("BVA skipped: both minimum and maximum are required.", file=sys.stderr)
    if not boundary_analysis:
        print("No supported explicit numeric boundaries found.", file=sys.stderr)
    print("[2/3] Generating test scenarios...", file=sys.stderr)
    scenarios = generate_scenarios(analysis)
    for scenario in scenarios.scenarios:
        scenario.scenario_id = id_generator.next_scenario_id()
        scenario.requirement_id = analysis.requirement_id
    print("[3/3] Generating detailed test cases...", file=sys.stderr)
    if demo_limits.active() and len(scenarios.scenarios) > 1:
        # Each scenario's model request is independent. Bounded parallelism makes
        # the public request-based demo fit its platform deadline while results
        # remain processed in scenario order below for stable IDs and QA output.
        with ThreadPoolExecutor(max_workers=min(2, len(scenarios.scenarios))) as executor:
            futures = []
            for scenario in scenarios.scenarios:
                context = contextvars.copy_context()
                futures.append(executor.submit(context.run, generate_test_cases, analysis, scenario))
            generated_responses = [future.result() for future in futures]
    else:
        generated_responses = [generate_test_cases(analysis, scenario)
                               for scenario in scenarios.scenarios]

    cases = []
    reports = []
    for scenario, response in zip(scenarios.scenarios, generated_responses):
        for case in response.test_cases:
            case.test_case_id = id_generator.next_test_case_id()
            case.requirement_id = analysis.requirement_id
            case.scenario_id = scenario.scenario_id
            report = validate_test_case(case, analysis.requirement_id, scenario.scenario_id)
            if case.test_type != scenario.scenario_type:
                report["errors"].append("Test case type must match its scenario type.")
                report["valid"] = False
            reports.append({"test_case_id": case.test_case_id, **report})
            status = "passed" if report["valid"] else "failed"
            print(f"{case.test_case_id} {status} validation", file=sys.stderr)
            for error in report["errors"]:
                print(f"  ERROR: {error}", file=sys.stderr)
            for warning in report["warnings"]:
                print(f"  WARNING: {warning}", file=sys.stderr)
            cases.append(case)
    duplicates = find_duplicate_titles(cases)
    for report in reports:
        if report["test_case_id"] in duplicates:
            report["warnings"].append("Exact duplicate title found.")
    print("\n===== DUPLICATE CHECK =====", file=sys.stderr)
    print("Duplicate test cases found: " + ", ".join(duplicates) if duplicates
          else "No exact duplicate titles found.", file=sys.stderr)
    summary = {"total_test_cases": len(cases),
               "valid_test_cases": sum(r["valid"] for r in reports),
               "invalid_test_cases": sum(not r["valid"] for r in reports),
               "exact_duplicates": len(duplicates)}
    print("\n===== VALIDATION SUMMARY =====", file=sys.stderr)
    for label, count in summary.items():
        print(f"{label.replace('_', ' ').title()}: {count}", file=sys.stderr)
    return {
        "requirement": requirement,
        "analysis": analysis.model_dump(),
        "boundary_analysis": boundary_analysis,
        "scenarios": scenarios.model_dump()["scenarios"],
        "test_cases": [case.model_dump() for case, report in zip(cases, reports) if report["valid"]],
        "rejected_test_cases": [case.model_dump() for case, report in zip(cases, reports) if not report["valid"]],
        "validation_results": reports,
        "duplicate_test_case_ids": duplicates,
        "validation_summary": summary,
        "evaluation": evaluate_test_suite(cases, scenarios.scenarios).model_dump(),
    }


def print_test_cases(test_cases):
    print("===== GENERATED TEST CASES =====\n")


    for test_case in test_cases:

        print("Test Case:", test_case.test_case_id)

        print(
            "Requirement:",
            test_case.requirement_id
        )

        print(
            "Scenario:",
            test_case.scenario_id
        )

        print("Title:", test_case.title)

        print("Type:", test_case.test_type)

        print("Priority:", test_case.priority)

        print("Test Data:", test_case.test_data)

        print("Steps:")

        for number, step in enumerate(
            test_case.steps,
            start=1
        ):
            print(f"  {number}. {step}")

        print(
            "Expected:",
            test_case.expected_result
        )

        print("-" * 70)

def run_document_pipeline(file_path):
    extracted = extract_requirements(read_document(file_path))
    if not extracted.requirements:
        raise ValueError("No testable requirements found in the document.")
    first = extracted.requirements[0]
    print(f"Extracted {len(extracted.requirements)} requirements; processing only "
          f"the first: {first.source_id}", file=sys.stderr)
    result = run_pipeline(first.requirement_text)
    result["source_document"] = str(file_path)
    result["source_id"] = first.source_id
    result["extracted_requirements"] = extracted.model_dump()["requirements"]
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate scenarios and test cases from a requirement.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--requirement", help="Requirement text")
    source.add_argument("--file", type=Path, help="UTF-8 requirement text file")
    source.add_argument("--document", type=Path, help="TXT/DOCX/PDF BRD: extract requirements and process only the first")
    parser.add_argument("--output", type=Path, help="Save the complete result as JSON")
    args = parser.parse_args(argv)
    interactive = args.requirement is None and args.file is None and args.document is None
    try:
        if args.document is not None:
            requirement = None
        elif args.file is not None:
            requirement = args.file.read_text(encoding="utf-8-sig")
        elif args.requirement is not None:
            requirement = args.requirement
        else:
            print("===== TestGen AI =====")
            requirement = input("Enter your requirement: ")
        result = run_document_pipeline(args.document) if args.document is not None else run_pipeline(requirement)
        rendered = json.dumps(result, indent=2, ensure_ascii=False)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
            print(f"Saved results to {args.output}", file=sys.stderr)
        if interactive:
            print_test_cases([TestCase.model_validate(case) for case in result["test_cases"]])
        else:
            print(rendered)
        return 1 if result["validation_summary"]["invalid_test_cases"] else 0
    except APIError as exc:
        print(f"Generation failed: provider request failed ({type(exc).__name__}). "
              "Check your API key, model availability and connection.", file=sys.stderr)
    except (ValueError, OSError, EOFError) as exc:
        print(f"Generation failed: {exc}", file=sys.stderr)
    except KeyboardInterrupt:
        print("Generation cancelled.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
