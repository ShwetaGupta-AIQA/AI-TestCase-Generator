from pathlib import Path
from services.document_reader import read_document


if __name__ == "__main__":
    print("===== EXTRACTED DOCUMENT =====\n")
    print(read_document(Path(__file__).parent / "sample_documents/login_brd.txt"))
