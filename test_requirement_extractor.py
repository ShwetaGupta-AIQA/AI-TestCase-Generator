from pathlib import Path
from services.document_reader import read_document
from services.requirement_extractor import extract_requirements


if __name__ == "__main__":
    result = extract_requirements(read_document(Path(__file__).parent / "sample_documents/login_brd.txt"))
    print("===== EXTRACTED REQUIREMENTS =====\n")
    for requirement in result.requirements:
        print("Source ID:", requirement.source_id)
        print("Requirement:", requirement.requirement_text)
        print("-" * 60)
