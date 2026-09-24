"""Lesson 10: export the first two document requirements to Excel."""
import argparse
from pathlib import Path
import sys

from openai import APIError
from app import run_pipeline
from models.requirement import RequirementAnalysis
from models.test_scenario import TestScenario
from models.test_case import TestCase
from services.document_reader import read_document
from services.requirement_extractor import extract_requirements
from services.excel_exporter import export_to_excel
from utils.id_generator import IDGenerator


def run_document_pipeline(file_path, output_file="TestGen_Output.xlsx"):
    print("Extracting requirements...", file=sys.stderr)
    extracted = extract_requirements(read_document(file_path))
    if not extracted.requirements:
        raise ValueError("No testable requirements found in the document.")
    ids = IDGenerator()
    requirements, scenarios, cases, results = [], [], [], []
    for source in extracted.requirements[:2]:
        print(f"Processing: {source.source_id}", file=sys.stderr)
        result = run_pipeline(source.requirement_text, id_generator=ids)
        results.append({"source_id": source.source_id, **result})
        requirements.append({"source": source, "analysis": RequirementAnalysis.model_validate(result["analysis"])})
        scenarios.extend(TestScenario.model_validate(s) for s in result["scenarios"])
        cases.extend(TestCase.model_validate(c) for c in result["test_cases"])
    output = export_to_excel(requirements, scenarios, cases, output_file)
    return {"output_file": output, "results": results,
            "extracted_count": len(extracted.requirements), "processed_count": len(results)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document", type=Path, default=Path(__file__).parent / "sample_documents/login_brd.txt")
    parser.add_argument("--output", type=Path, default=Path("TestGen_Output.xlsx"))
    args = parser.parse_args(argv)
    try:
        result = run_document_pipeline(args.document, args.output)
        print(f"Excel created: {result['output_file']} (processed {result['processed_count']} of {result['extracted_count']} requirements)")
        return 1 if any(r["rejected_test_cases"] for r in result["results"]) else 0
    except APIError as exc:
        print(f"Generation failed: provider request failed ({type(exc).__name__}).", file=sys.stderr)
    except (ValueError, OSError) as exc:
        print(f"Export failed: {exc}", file=sys.stderr)
    except KeyboardInterrupt:
        print("Generation cancelled.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
