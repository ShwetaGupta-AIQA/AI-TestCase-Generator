"""Local text extraction. Scanned PDFs require OCR, which is not included."""
from pathlib import Path
from zipfile import BadZipFile, ZipFile
from services import demo_limits

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from pypdf import PdfReader
from pypdf.errors import PyPdfError


def read_txt(file_path):
    return Path(file_path).read_text(encoding="utf-8-sig")


def read_docx(file_path):
    if demo_limits.active():
        with ZipFile(file_path) as archive:
            if sum(item.file_size for item in archive.infolist()) > 20_000_000:
                raise demo_limits.DemoLimitError("Expanded DOCX exceeds the demo limit of 20 MB.")
    document = Document(file_path)
    parts = []
    # Include tables: BRDs often store their requirements in cells.
    from docx.table import Table
    for block in document.iter_inner_content():
        if isinstance(block, Table):
            parts.extend("\t".join(cell.text for cell in row.cells) for row in block.rows)
        elif block.text.strip():
            parts.append(block.text)
    return "\n".join(parts)


def read_pdf(file_path):
    with open(file_path, "rb") as source:
        reader = PdfReader(source)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError("Password-protected PDFs are not supported.")
        if demo_limits.active() and len(reader.pages) > 20:
            raise demo_limits.DemoLimitError("Demo PDFs must contain at most 20 pages.")
        return "\n".join(page.extract_text() or "" for page in reader.pages)


def read_document(file_path):
    path = Path(file_path)
    readers = {".txt": read_txt, ".docx": read_docx, ".pdf": read_pdf}
    reader = readers.get(path.suffix.lower())
    if reader is None:
        raise ValueError(f"Unsupported file type: {path.suffix}. Use TXT, DOCX or PDF.")
    if not path.is_file():
        raise ValueError(f"Document file not found: {path}")
    try:
        text = reader(path)
    except (UnicodeError, BadZipFile, PackageNotFoundError, PyPdfError, KeyError) as exc:
        raise ValueError(f"Cannot read {path.name}: invalid or unsupported document content.") from exc
    if not text.strip():
        raise ValueError("Document contains no extractable text. Scanned PDFs need OCR (not supported).")
    if demo_limits.active() and len(text) > demo_limits.MAX_DOCUMENT_CHARS:
        raise demo_limits.DemoLimitError("Document text exceeds the demo limit of 30,000 characters.")
    demo_limits.remaining()
    return text
