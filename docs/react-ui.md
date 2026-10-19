# React quality workspace

The React frontend provides requirement generation, document upload, API test design/review/exports, public-page browser-test drafting, and saved generation runs in one interface. It reuses the existing FastAPI contracts and separate generation worker.

## Local startup

Use the project's Python 3.14 environment and installed backend requirements. From the repository root, start the full API:

```powershell
.venv/Scripts/python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

In another root terminal, start the worker:

```powershell
.venv/Scripts/python.exe -m runs.worker
```

In a third terminal:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

Open http://127.0.0.1:5173. Node.js 24 is the verified frontend runtime. Generation requires a configured AI provider in the backend environment. API contract design is deterministic and requires no provider call. Keep API keys on the server.

Vite forwards same-origin `/api` requests to `http://127.0.0.1:8000`. To change that destination, copy `frontend/.env.example` to `frontend/.env.local`, edit `TESTGEN_API_PROXY`, and restart Vite. The browser does not receive provider credentials. No general cross-origin CORS opening is needed.

## Docker

`docker compose up --build` now includes the React frontend at localhost:5173, the full API, the existing worker and PostgreSQL. Nginx forwards API requests and workspace headers; route fallback supports direct links. Streamlit remains available with `docker compose --profile legacy-ui up --build` at localhost:8501.

The existing public Streamlit/Vercel demo is not automatically replaced. A static React host must reverse-proxy `/api` to a deployed backend. Full features need the durable API, database and running worker; a serverless guest endpoint alone does not provide them. Review access controls and provider-cost limits before public exposure.

## First workflow

1. Open Generate Tests. Use the example or upload TXT, DOCX or a text-based PDF. Scanned PDFs need OCR.
2. Submit once. The UI polls the durable run until completion, with status/error recovery. A queued run needs the worker.
3. Review requirements, scenarios, accepted/rejected cases, quality checks and generated traceability. Search/filter test cases and download the workbook.
4. API Testing supports manual endpoints, OpenAPI 3.0/3.1 JSON/YAML or URL import, HTML/API documentation and endpoint contract review. Select cases, adjust status/result/priority, inspect top-level field links, acknowledge review, and export Excel, Postman, Pytest or experimental SoapUI. Executable exports require confirmed status codes. Counts are designed tests, not executed coverage.
5. Web UI Testing inspects a public HTTPS page. Review observed controls, actions and assertions, edit titles/objectives, select cases and confirm review before Playwright export. Rendered inspection is enabled only if advertised by the backend. No exported suite is run by this screen.
6. Run History reopens saved requirement-generation runs and downloads completed workbooks. API/browser draft editors remain in tab memory while navigating; they are not saved-run records. Reloading clears those drafts.

## Workspace isolation and guest mode

`GET /capabilities` returns feature flags, limits, workspace requirements and rendered-browser availability. The full API advertises all major workflows. The limited guest API advertises generation/upload only; the UI hides unsupported navigation and labels its session-only results.

When `TESTGEN_REQUIRE_WORKSPACE=true`, use Help & Setup to create or restore a private workspace. Its recovery token is held in the tab's session storage, sent in `X-TestGen-Workspace`, and used for authenticated fetch downloads. Keep a private copy before closing the tab. Switching workspace clears UI drafts; restoration validates the token with the backend first. Workspace tokens isolate saved runs but are not a full identity/login system. Trusted local mode retains the existing shared local workspace behaviour.

Only the capability endpoint was added to the API. Existing generation, worker, validation/export logic and Streamlit remain compatible. Private/failed/error states are displayed; the UI never invents completed generation metrics.

## Verification

Run `npm.cmd test` and `npm.cmd run build` from frontend, and the existing Python pytest suite from the root. CI adds frontend tests/build, dependency auditing and an image-build check. Browser checks use synthetic fixtures for AI generation, so they make no claims about real provider quality.

Initial verification: 136 Python tests and 52 subtests, 14 frontend tests, TypeScript/Vite build, and the React/Nginx image build passed. The frontend audit reported zero known vulnerabilities at verification time. The browser check passed seven flow groups with no page errors, including real API design/Excel export, synthetic generation/polling/traceability, history reopening, a synthetic browser draft with real backend Playwright export, and mobile navigation without horizontal overflow.

To reproduce browser checks, start the trusted-local full API and React at the default ports, then run `.venv/Scripts/python.exe -m playwright install chromium` and `.venv/Scripts/python.exe scripts/check_react_ui.py`. Generated screenshots and export artifacts stay under ignored `output/react-ui-checks`. These tests do not call an AI provider. The actual full Docker stack and a real provider generation run were not exercised by these UI checks; only the frontend image build was verified.
