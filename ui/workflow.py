"""UI workflows with isolated temporary files and downloadable workbook bytes."""
from pathlib import Path
import tempfile

from app import run_pipeline
from document_pipeline import run_document_pipeline
from models.document_requirement import ExtractedRequirement
from models.requirement import RequirementAnalysis
from models.test_scenario import TestScenario
from models.test_case import TestCase
from services.excel_exporter import export_to_excel


def generate_document(filename, content):
    extension = Path(filename).suffix.lower()
    if extension not in {".txt", ".docx", ".pdf"}:
        raise ValueError("Choose a TXT, DOCX or PDF document.")
    if not content:
        raise ValueError("The uploaded document is empty.")
    if len(content) > 10 * 1024 * 1024:
        raise ValueError("Choose a document smaller than 10 MiB.")
    with tempfile.TemporaryDirectory(prefix="testgen-ui-") as directory:
        source = Path(directory) / ("document" + extension)
        source.write_bytes(content)
        output = Path(directory) / "TestGen_Output.xlsx"
        report = run_document_pipeline(source, output)
        report["excel_data"] = output.read_bytes()
        report.pop("output_file", None)
    return report


def generate_manual(requirement):
    if len(requirement.strip()) < 5:
        raise ValueError("Enter a requirement containing at least five characters.")
    result = run_pipeline(requirement.strip())
    result["source_id"] = "SOURCE-001"
    requirements = [{"source": ExtractedRequirement(source_id="SOURCE-001", requirement_text=requirement.strip()),
                     "analysis": RequirementAnalysis.model_validate(result["analysis"])}]
    with tempfile.TemporaryDirectory(prefix="testgen-ui-") as directory:
        path = Path(directory) / "TestGen_Output.xlsx"
        export_to_excel(requirements,
                        [TestScenario.model_validate(s) for s in result["scenarios"]],
                        [TestCase.model_validate(c) for c in result["test_cases"]], path)
        data = path.read_bytes()
    return {"results": [result], "extracted_count": 1, "processed_count": 1, "excel_data": data}


def generate_manual_to_file(requirement, output_path):
    """Generate the serializable report used by durable workers."""
    if len(requirement.strip()) < 5:
        raise ValueError("Enter a requirement containing at least five characters.")
    result = run_pipeline(requirement.strip())
    result["source_id"] = "SOURCE-001"
    requirements = [{"source": ExtractedRequirement(source_id="SOURCE-001", requirement_text=requirement.strip()),
                     "analysis": RequirementAnalysis.model_validate(result["analysis"])}]
    export_to_excel(requirements,
                    [TestScenario.model_validate(s) for s in result["scenarios"]],
                    [TestCase.model_validate(c) for c in result["test_cases"]], output_path)
    return {"results": [result], "extracted_count": 1, "processed_count": 1}
