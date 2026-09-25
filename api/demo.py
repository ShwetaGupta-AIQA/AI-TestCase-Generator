"""Stateless public-demo API: python -m uvicorn api.demo:app.

Deliberately does not import api.main or runs: no database, worker or saved history.
"""
import base64
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from openai import APIError
from pydantic import BaseModel, ConfigDict, Field

from services import demo_limits as limits
from services.provider_errors import provider_error_message
from ui.workflow import generate_document, generate_manual

app = FastAPI(title="TestGen AI Demo API", version="1.0.0",
              description="Bounded generation with session-only results; no saved run history.")


class DemoRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    requirement: str = Field(min_length=5, max_length=limits.MAX_TEXT_CHARS)


@app.middleware("http")
async def request_limits(request, call_next):
    # Bound actual streamed body bytes too, including chunked requests, before
    # multipart parsing can spool an unbounded upload to temporary disk.
    if request.method == "POST":
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > limits.MAX_UPLOAD_BYTES + 100_000:
                return JSONResponse(status_code=413, content={"detail": "Demo request is too large."})
            chunks.append(chunk)
        request._body = b"".join(chunks)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(limits.DemoLimitError)
async def limit_error(request, exc):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(limits.DemoTimeoutError)
async def timeout_error(request, exc):
    return JSONResponse(status_code=504, content={"detail": str(exc)})


@app.exception_handler(APIError)
async def provider_error(request, exc):
    return JSONResponse(status_code=502, content={"detail": provider_error_message(exc)})


@app.exception_handler(ValueError)
async def invalid_output(request, exc):
    return JSONResponse(status_code=502, content={"detail": "Generation could not complete. Check the document or try a shorter requirement."})


@app.exception_handler(OSError)
async def file_error(request, exc):
    return JSONResponse(status_code=503, content={"detail": "Temporary document or workbook processing is unavailable."})


@app.get("/")
def root():
    return {"message": "TestGen AI Demo API", "mode": "demo"}


@app.get("/health")
def health():
    return {"status": "healthy", "mode": "demo"}


def response_for(report):
    payload = {key: value for key, value in report.items() if key != "excel_data"}
    payload["excel_base64"] = base64.b64encode(report["excel_data"]).decode("ascii")
    payload["demo_notice"] = "Session-only results. Up to two requirements, three scenarios per requirement and three cases per scenario."
    response = JSONResponse(payload, headers={"Cache-Control": "no-store"})
    if len(response.body) > limits.MAX_RESPONSE_BYTES:
        raise limits.DemoLimitError("Generated report is too large for this demo. Try a shorter requirement.")
    limits.remaining()
    return response


@app.post("/generate")
def generate(request: DemoRequest):
    with limits.demo_budget():
        return response_for(generate_manual(request.requirement))


@app.post("/generate-document")
def document(file: UploadFile = File(...)):
    try:
        if Path(file.filename or "").suffix.lower() not in {".txt", ".docx", ".pdf"}:
            raise HTTPException(400, "Only TXT, DOCX and text-based PDF documents are supported.")
        content = file.file.read(limits.MAX_UPLOAD_BYTES + 1)
        if len(content) > limits.MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Demo upload limit is 4 MB.")
        if not content:
            raise HTTPException(400, "Document is empty.")
        with limits.demo_budget():
            return response_for(generate_document(file.filename, content))
    finally:
        file.file.close()
