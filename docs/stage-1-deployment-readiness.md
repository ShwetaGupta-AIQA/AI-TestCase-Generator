# Stage 1.1 - Deployment readiness review

Reviewed: 24 September 2026. Local checkout: `4b8f4ff`.
Configured GitHub remote: https://github.com/ShwetaGupta-AIQA/AI-TestCase-Generator

## Verdict

**CHANGE REQUIRED before deploying Streamlit Community Cloud + FastAPI on Vercel.**
The core generation and deterministic QA services can be reused. The current UI
depends on a database-backed queue, a separately running worker, and shared files.
Deploying the API alone does not execute queued jobs. Calling this history
"temporary" does not remove that dependency.

This review covers the local checkout and official hosting documentation. Remote
branch parity, cloud builds, account quotas, live model latency and hosted behavior
have not been verified. No application code or deployment was changed in this step.

## READY / CHANGE REQUIRED checklist

READY means the relevant code is present, not that cloud execution is certified.

| Area | Status | Evidence and required action |
| --- | --- | --- |
| FastAPI entry point | CHANGE REQUIRED | `api/main.py` exports `app`; root `app.py` is the pipeline/CLI. Configure an explicit Vercel entry point; do not rename the pipeline merely for discovery. |
| Streamlit entry point | READY | `ui/streamlit_app.py` explicitly adds the project root to the Python path. |
| Production API URL | READY | `ui/api_client.py` reads `TESTGEN_API_URL`; loopback is only the local default. Supply the HTTPS URL in cloud settings. |
| Environment and secrets | READY | OpenRouter key/model come from environment variables. `.env` and Streamlit secrets are ignored; only `.env.example` is tracked among checked secret filenames. This is not a historical secret audit. |
| Worker execution | CHANGE REQUIRED | UI posts to `/runs` and `/runs/document`; `runs/worker.py` polls indefinitely in a separate process. The proposed two-host deployment has no host/process configured for it. |
| Database initialization | CHANGE REQUIRED | API imports `runs.database`, which creates an engine at import time; startup initializes tables. Default SQLite creates `output/` under the source tree. A stateless demo must avoid this import/startup dependency. |
| Files and downloads | CHANGE REQUIRED | `runs/repository.py` fixes storage at `output/runs`; download routes require the worker's files. Use request-local temporary files and return results/workbook to the UI session for the demo. Moving SQLite to `/tmp` is not a shared-storage solution. |
| Upload size | CHANGE REQUIRED | UI/API allow 10 MiB. Choose a lower demo cap, such as 4,000,000 bytes, allowing multipart overhead under Vercel's 4.5 MB request limit. Enforce it in both UI and API. |
| Parsed document size | CHANGE REQUIRED | Readers support TXT/DOCX/text PDFs and reject empty/unreadable content, but lack parsed-text/page limits. A small compressed file can still expand to substantial input. |
| Generation duration | CHANGE REQUIRED | One requirement makes analysis + scenario + one call per scenario. Each call has a 60-second SDK timeout, with retries disabled. There is no overall deadline or enforced scenario count. Bound total work and measure live duration. |
| HTTP client timeout | CHANGE REQUIRED | The current 15-second timeout suits queue submission/polling. Request-based generation needs a separate bounded timeout coordinated with the server deadline. |
| Dependencies/runtime | CHANGE REQUIRED | Local Python is 3.14.7; the frozen requirements include UI-heavy packages. Verify Linux installation and deployed bundle size; select the cloud Python version explicitly and separate API dependencies if needed. |
| Excel generation | READY | `ui/workflow.py` already creates workbooks in isolated temporary directories and returns bytes. Reuse this behavior; validate total response size and retain bytes in the UI session. |
| QA and traceability | READY | Pipeline assigns IDs, validates cases, computes BVA/metrics and excludes rejected cases from Excel. Preserve these semantics in the demo adapter. |
| CORS | READY | Streamlit calls the API from Python via HTTPX, not directly from browser JavaScript. Cross-origin browser CORS permission is not required for this path. |
| Public run history | CHANGE REQUIRED | `/runs` lists all runs without ownership checks. A public stateless demo should not expose durable history/download routes or another visitor's data. |
| Provider errors | READY | Sanitized provider/generation error handling exists. Verify quota, timeout and malformed-response behavior through the hosted UI. |
| Public-demo controls | CHANGE REQUIRED | Add input length, generation/output bounds and a sample requirement button. Current text models have a minimum length but no maximum; scenario/case lists lack maximum counts. |
| Documentation | CHANGE REQUIRED | `docs/architecture.md` contains placeholders and a simplified chain. README still says the UI calls services directly, but active UI uses the queue API. Release checklist predates Compose and the configured Git remote. Reconcile these after selecting the demo behavior. |

## Proposed smallest adaptation for the planned hosts

Keep the reusable analysis, generation, QA, ID, metrics and Excel code. Add an
explicit stateless demo mode alongside the existing local/Compose durable mode:

1. Load a FastAPI demo application without importing or initializing run storage.
   Keep health and API documentation available; expose bounded generation routes.
2. Run generation during the request, with an overall deadline, bounded scenario
   and case counts, and bounded document/text input. Do not silently label truncated
   processing as full coverage.
3. Return the report and workbook in the completed response (for example, an
   explicitly size-checked base64 workbook field). Allow for encoding overhead
   and the platform response limit. Temporary files are cleaned after reading.
4. Let Streamlit retain report/workbook in its own session and download bytes
   directly. Hide durable run history and URL-based run recovery in this mode.
   Explain that refresh/session loss may clear results and a restart loses them.
5. Keep OpenRouter credentials on the API host. Streamlit needs the backend URL.
   No PostgreSQL or Redis is required for this proposed demo mode.
6. Configure the selected API entry point and Python version, then validate a
   clean Linux build and a bounded live generation before publishing links.

This is a recommendation, not an implemented or validated architecture. If live
generation cannot reliably fit the request budget, stop this hosting path and
reconsider a host for the existing worker architecture. Increasing an HTTP client
timeout alone will not solve a server execution limit.

## Hosting facts checked

- Vercel supports an explicit `tool.vercel.entrypoint` in `pyproject.toml`, so the
  existing module layout need not be reorganized for discovery.
  [FastAPI deployment](https://vercel.com/docs/frameworks/backend/fastapi)
- Vercel documents Python 3.12, 3.13 and 3.14, and a standard 500 MB uncompressed
  Python bundle limit. Validate the actual dependency bundle rather than assuming
  the Windows freeze installs successfully on Linux.
  [Python runtime](https://vercel.com/docs/functions/runtimes/python)
- With Fluid Compute, the documented Hobby duration maximum is 300 seconds.
  Request and response payloads are limited to 4.5 MB. Check the actual project
  configuration before setting an application deadline below that ceiling.
  [Function limits](https://vercel.com/docs/functions/limitations)
- Function source filesystems are read-only, with writable temporary scratch space.
  Treat scratch files as disposable and never depend on sharing them across calls.
  [Runtimes](https://vercel.com/docs/functions/runtimes)
- Streamlit Community Cloud accepts secrets through application settings.
  [Secrets management](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)
- OpenRouter free usage is quota-limited. One user generation consumes multiple
  model requests. Confirm the account's actual allowance and handle exhaustion;
  zero hosting cost does not guarantee uninterrupted inference availability.
  [Provider limits](https://openrouter.ai/docs/api/reference/limits)

## Validation and next steps

- Existing virtual environment: Python 3.14.7; `pip check` passed.
- Regression suite: 62 of 63 tests passed; one Streamlit session-restoration test
  exceeded its three-second AppTest timeout. A focused rerun of all six UI tests
  passed. Treat this as a timing-sensitive test pending stabilization, not a fully
  green full-suite run. Logs: `.tmp/stage1-tests.log` and `.tmp/stage1-ui-tests.log`.
  The full suite used a separate SQLite database under `.tmp` to avoid altering
  existing queued runs. Tests required execution outside the sandbox because
  Windows denied temporary-file access inside it.
- System `python` lacks project dependencies; use `.venv/Scripts/python.exe`.
- Docker is not available on PATH; Docker/Linux execution remains unverified.
- No live model calls, cloud deployment, Git push or public URL verification done.

Implementation order: demo execution/storage adapter; bounded generation and
client behavior; cloud entry point/dependencies/secrets documentation; local
regressions and Linux build; live timing; deployment; hosted end-to-end checks;
README/screenshots and recruiter review.

Stage 1.1 delivers this checklist. Stage 1 remains incomplete until public input,
generation, QA/BVA, traceability, workbook download and API docs all work.

## Follow-up implementation

The stateless demo adapter is now implemented locally with explicit `api.demo:app`
and `TESTGEN_MODE=demo` entry points. See [demo setup and limits](stage-1-demo-mode.md).
The findings above describe the original reviewed checkout; cloud builds, live
timing and deployment remain outstanding. The cooperative deadline is not a hard
process-cancellation guarantee.
