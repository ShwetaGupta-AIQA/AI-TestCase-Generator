from pathlib import Path
from services.document_reader import read_document
from services.requirement_extractor import extract_requirements
from services.requirement_analyzer import analyze_requirement
from utils.id_generator import IDGenerator


if __name__ == "__main__":
    extracted = extract_requirements(read_document(Path(__file__).parent / "sample_documents/login_brd.txt"))
    if not extracted.requirements:
        raise SystemExit("No testable requirements found in the document.")
    first = extracted.requirements[0]
    print("Source Requirement:", first.source_id)
    print(first.requirement_text)
    analysis = analyze_requirement(first.requirement_text)
    analysis.requirement_id = IDGenerator().next_requirement_id()
    print("System ID:", analysis.requirement_id)
    print("Functionality:", analysis.functionality)
    print("Business Rules:", analysis.business_rules)
    print("Missing Information:", analysis.missing_information)
