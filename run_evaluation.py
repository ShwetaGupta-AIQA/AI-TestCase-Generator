"""Run three golden boundary-extraction examples against the configured model."""
import argparse
import json
import os
from pathlib import Path
from datetime import datetime, timezone

from openai import APIError
from pydantic import ValidationError
from evaluation.evaluation_dataset import EVALUATION_DATASET
from evaluation.evaluator import evaluate_boundary_extraction
from services.requirement_analyzer import analyze_requirement


def run_evaluation(dataset=None):
    dataset = EVALUATION_DATASET if dataset is None else dataset
    results = []
    for item in dataset:
        row = {"id": item["id"], "requirement": item["requirement"],
               "expected": {k: item[k] for k in ("expected_minimum", "expected_maximum", "expected_unit")},
               "passed": False, "schema_valid": False}
        try:
            analysis = analyze_requirement(item["requirement"])
            row["schema_valid"] = True
            row["actual"] = [b.model_dump() for b in analysis.boundary_constraints]
            row["passed"] = evaluate_boundary_extraction(analysis, item["expected_minimum"],
                                                         item["expected_maximum"], item["expected_unit"])
        except (APIError, ValueError) as exc:
            row["error"] = type(exc).__name__
            # Transport/configuration failures cannot establish schema validity.
            if isinstance(exc, APIError) or (not isinstance(exc, ValidationError) and "OPENROUTER_API_KEY" in str(exc)):
                row["schema_valid"] = None
        results.append(row)
    total = len(results)
    passed = sum(row["passed"] for row in results)
    assessed = [row for row in results if row["schema_valid"] is not None]
    return {"dataset_version": "v1", "model": os.getenv("OPENROUTER_MODEL", "openrouter/free"),
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "total": total, "passed": passed, "failed": total - passed,
            "boundary_extraction_accuracy": round(passed / total * 100, 2) if total else 0.0,
            "schema_validity_score": round(sum(r["schema_valid"] for r in assessed) / len(assessed) * 100, 2) if assessed else None,
            "schema_assessed_examples": len(assessed), "results": results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Save the measured results as JSON")
    args = parser.parse_args(argv)
    report = run_evaluation()
    for row in report["results"]:
        print(f"{row['id']}: {'PASS' if row['passed'] else 'FAIL'}")
        if not row["passed"]:
            print("Actual:", row.get("actual", row.get("error")))
    print(f"Total: {report['total']} | Passed: {report['passed']} | Failed: {report['failed']}")
    print(f"Boundary Extraction Accuracy (dataset v1): {report['boundary_extraction_accuracy']:.2f}%")
    print("Schema Validity:", report["schema_validity_score"])
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
