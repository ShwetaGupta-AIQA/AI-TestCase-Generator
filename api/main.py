"""Run with: python -m uvicorn api.main:app --reload"""
from pathlib import Path
import tempfile

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from openai import APIError
from sqlalchemy.exc import SQLAlchemyError
from services.provider_errors import provider_error_message

from app import run_pipeline
from models.api_models import RequirementRequest, RunRequest, ScenarioResponse, DocumentUploadResponse
from models.requirement import RequirementAnalysis
from services.document_reader import read_document
from services.requirement_extractor import extract_requirements
from services.requirement_analyzer import analyze_requirement
from services.scenario_generator import generate_scenarios
from utils.id_generator import IDGenerator
from runs.database import init_database
from runs.repository import create_run, get_run, list_runs, run_directory, serialize


app = FastAPI(title="TestGen AI API", description="AI-powered test case generation platform", version="1.0.0")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@app.on_event("startup")
def initialize():
    init_database()


@app.exception_handler(APIError)
async def provider_error(request, exc):
    return JSONResponse(status_code=502, content={"detail": provider_error_message(exc)})


@app.exception_handler(ValueError)
async def generation_error(request, exc):
    # Do not expose raw model responses or provider credentials in HTTP errors.
    return JSONResponse(status_code=502, content={"detail": "AI generation returned invalid output or is not configured. Check server configuration and retry."})


@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    return JSONResponse(status_code=503, content={"detail": "Run storage is temporarily unavailable."})


@app.get("/")
def root():
    return {"message": "TestGen AI API is running"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/analyze-requirement", response_model=RequirementAnalysis)
def analyze_requirement_api(request: RequirementRequest):
    analysis = analyze_requirement(request.requirement)
    analysis.requirement_id = IDGenerator().next_requirement_id()
    return analysis


@app.post("/generate-scenarios", response_model=ScenarioResponse)
def generate_scenarios_api(request: RequirementRequest):
    ids = IDGenerator()
    analysis = analyze_requirement(request.requirement)
    analysis.requirement_id = ids.next_requirement_id()
    scenarios = generate_scenarios(analysis)
    for scenario in scenarios.scenarios:
        scenario.scenario_id = ids.next_scenario_id()
        scenario.requirement_id = analysis.requirement_id
    return {"requirement_analysis": analysis, "scenarios": scenarios.scenarios}


@app.post("/generate-test-cases")
def generate_test_cases_api(request: RequirementRequest):
    result = run_pipeline(request.requirement)
    # Match the lesson's API contract while retaining QA/BVA reports.
    return {**result, "requirement_text": result["requirement"], "requirement": result["analysis"]}


@app.post("/upload-document", response_model=DocumentUploadResponse)
def upload_document(file: UploadFile = File(...)):
    # Sync route runs in FastAPI's thread pool, including blocking model calls.
    extension = Path(file.filename or "").suffix.lower()
    try:
        if extension not in {".txt", ".docx", ".pdf"}:
            raise HTTPException(400, "Only TXT, DOCX and PDF files are supported.")
        with tempfile.TemporaryDirectory(prefix="testgen-upload-") as directory:
            path = Path(directory) / ("document" + extension)
            size = 0
            with path.open("wb") as destination:
                while chunk := file.file.read(64 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise HTTPException(413, "Document exceeds the 10 MiB limit.")
                    destination.write(chunk)
            try:
                text = read_document(path)
            except (ValueError, OSError) as exc:
                raise HTTPException(400, "Document is empty, unreadable or unsupported. Scanned PDFs require OCR.") from exc
            extracted = extract_requirements(text)
            return {"filename": file.filename, "requirements_found": len(extracted.requirements),
                    "requirements": extracted.requirements}
    finally:
        file.file.close()


@app.post("/runs", status_code=202)
def submit_run(request: RunRequest):
    try:
        run, created = create_run(idempotency_key=request.idempotency_key, input_type="manual",
                                  input_text=request.requirement)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {**serialize(run), "created": created}


@app.post("/runs/document", status_code=202)
def submit_document_run(file: UploadFile = File(...), idempotency_key: str = Form(...)):
    extension = Path(file.filename or "").suffix.lower()
    try:
        if extension not in {".txt", ".docx", ".pdf"}:
            raise HTTPException(400, "Only TXT, DOCX and PDF files are supported.")
        content = file.file.read(MAX_UPLOAD_BYTES + 1)
        if not content:
            raise HTTPException(400, "Document is empty.")
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Document exceeds the 10 MiB limit.")
        try:
            run, created = create_run(idempotency_key=idempotency_key, input_type="document",
                                      filename=Path(file.filename or "document").name, content=content)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {**serialize(run), "created": created}
    finally:
        file.file.close()


@app.get("/runs")
def run_history(limit: int = 20):
    if not 1 <= limit <= 100:
        raise HTTPException(422, "Limit must be between 1 and 100.")
    return {"runs": [serialize(run) for run in list_runs(limit)]}


@app.get("/runs/{run_id}")
def run_status(run_id: str):
    run = get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found.")
    return serialize(run, include_result=True)


@app.get("/runs/{run_id}/download")
def download_run(run_id: str):
    run = get_run(run_id)
    if not run or run.status != "completed" or not run.excel_path:
        raise HTTPException(404, "Completed workbook not found.")
    path = Path(run.excel_path)
    # The path came from the worker, but still verify its resolved parent before serving.
    expected = run_directory(run.id).resolve()
    try:
        path.resolve().relative_to(expected)
    except ValueError as exc:
        raise HTTPException(404, "Completed workbook not found.") from exc
    if not path.is_file():
        raise HTTPException(404, "Completed workbook not found.")
    return FileResponse(path, filename="TestGen_Output.xlsx",
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
