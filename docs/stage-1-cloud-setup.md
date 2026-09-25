# Stage 1 - Cloud configuration

Status: Stage 1 public deployment is live and basic endpoint checks passed.

## Live endpoints

- Streamlit demo: https://testgen-ai-demo.streamlit.app/
- Vercel API health: https://ai-test-case-generator-chi.vercel.app/health
- Vercel API documentation: https://ai-test-case-generator-chi.vercel.app/docs

On 25 September 2026, the public Streamlit page returned HTTP 200. The API health
endpoint returned `{"status":"healthy","mode":"demo"}`; the API docs returned HTTP 200,
and OpenAPI listed only `/`, `/health`, `/generate`, and `/generate-document`.
This verifies availability and the intended stateless route surface, not a public
generation request or model-quality measurement.

## Vercel API

- Repository root: `.`. Framework: FastAPI.
- `pyproject.toml` selects Python 3.14 and `api.demo:app` explicitly. Its dependencies
  are API-only; Streamlit, PostgreSQL and the durable worker are not required.
- `vercel.json` sets a 300-second function ceiling. Enable/confirm Fluid Compute
  and check the selected plan supports that ceiling.
- `.vercelignore` excludes the full local `requirements.txt`/`requirements.in`
  so Vercel receives the API manifest, plus exclusions for secrets, local files,
  tests, UI entry point and durable run code. `ui/workflow.py` must remain because
  the API reuses its workbook helpers.
- Keep default install/build settings initially; do not override them with
  `pip install -r requirements.txt`. Confirm build logs use the API manifest.
- Configure `OPENROUTER_API_KEY` in Vercel environment settings and
  `OPENROUTER_MODEL=openrouter/free` initially. Check model availability with a
  live request. No database URL or worker configuration is required.
- Verify `/health` returns `mode: demo`, `/docs` lists `/generate` and
  `/generate-document`, and `/runs` returns 404.

The explicit module entry point is supported by
[Vercel FastAPI configuration](https://vercel.com/docs/frameworks/backend/fastapi).
Python selection and dependency manifests follow the
[Python runtime documentation](https://vercel.com/docs/functions/runtimes/python).
Deployment exclusions follow the
[.vercelignore documentation](https://vercel.com/docs/deployments/vercel-ignore).

## Streamlit Community Cloud

Use the same repository and select `ui/streamlit_app.py`. The full root
`requirements.txt` remains available to Streamlit and local/Docker development.
Choose Python 3.14 in advanced settings if offered; validate installation before
considering another Python version. Set these root-level values in cloud secrets:

```toml
TESTGEN_MODE = "demo"
TESTGEN_API_URL = "https://YOUR-ACTUAL-API-HOST.vercel.app"
```

Replace the placeholder only after the real API URL exists. The OpenRouter key
belongs to the API host; Streamlit does not need it. Check that the deployed API
is accessible from Streamlit; a protected preview URL may require additional
access configuration. Never use localhost as the cloud UI's API URL.

## Repeatable validation

For local Linux validation after Docker Desktop reports its Linux engine running:

```powershell
docker build -f Dockerfile.demo -t testgen-ai-demo .
docker run --rm --no-healthcheck testgen-ai-demo python scripts/check_demo_deployment.py
```

`Dockerfile.demo` uses Python 3.14 on Linux, installs only API dependencies, and
executes as a non-root user. The smoke check needs no API key and performs real
Excel IO with mocked model output. These commands do not publish an image or code.

From the repository root:

```powershell
.\.venv\Scripts\python.exe scripts/check_demo_deployment.py
```

This runs mocked generation through the real API and reopens the real workbook.
It verifies health/docs, absence of history, accepted cases and database-free
imports. It does not measure model performance.

After setting your key locally (do not paste it into chat), run:

```powershell
.\.venv\Scripts\python.exe scripts/check_demo_deployment.py --live
```

The live command sends one synthetic requirement to OpenRouter, potentially making
multiple model requests. It reports elapsed time, accepted-case count and response
size. A single successful sample is only a smoke check; repeat representative
manual/document flows and record timings before relying on the request deadline.

`.github/workflows/demo-linux.yml` installs API-only dependencies on Ubuntu/Python
3.14 and runs the mocked smoke check on pushes/PRs or manual dispatch. It has no
provider secrets and makes no model calls. It has been prepared, not executed here.
Actual Vercel build success is still required; CI is not a substitute for it.

## Outstanding evidence

- On 25 September 2026, after restarting Windows and installing WSL 2.7.13,
  Docker Desktop started its Linux x86_64 engine successfully.
- `docker build -f Dockerfile.demo -t testgen-ai-demo .` passed, including API-only
  dependency installation and `pip check` on Python 3.14 / Linux.
- The container smoke check passed as the image's non-root user: health/docs,
  absence of history routes, database-free imports, one accepted mocked test case,
  and an actual workbook reopened with all four expected sheets. Report size:
  11,877 bytes; smoke execution: 0.08 seconds (mocked, not live model latency).
  Logs: `.tmp/docker-demo-build.log` and `.tmp/docker-demo-smoke.log`.
  Image remains local as `testgen-ai-demo:latest`; the test container was removed.
- Linux wheel resolution/download passed on 24 September 2026 after retrying
  outside the sandbox with project-local `TEMP`/`TMP`. All 10 direct API pins and
  their dependencies resolved: 29 wheels for CPython 3.14 / Linux x86_64.
  Files are in `.tmp/linux-wheels`; output is in `.tmp/linux-dependencies.log`.
  No pip temporary-directory access errors occurred on the successful retry.
  This verifies wheel availability, not execution on Linux or a Vercel build.
  Unpinned transitive dependencies resolved newer versions in some cases (including
  Starlette 1.7.0 versus locally installed 1.6.0). The subsequent Linux container
  build and smoke check passed. The full pinned environment was also built using
  `Dockerfile` on 25 September 2026: **all 74 regression tests passed on Linux**
  in 4.163 seconds, using an isolated SQLite database and mocked model responses.
  Logs: `.tmp/docker-full-build.log` and `.tmp/docker-linux-regression.log`.
- A real Uvicorn process in the demo container passed localhost HTTP checks:
  `/health` returned healthy/demo, `/docs` returned 200, and OpenAPI exposed the
  demo generation routes. Docker's health check reported healthy. The temporary
  container was stopped and removed afterward.
- The local mocked deployment smoke check passed, returning an 11,889-byte report
  with an actual Excel workbook and one accepted case. All manifest dependency
  pins match the installed local environment; this does not verify Linux support.
- A live local smoke check passed on 24 September 2026 after allowing network
  access outside the sandbox: **102.57 seconds**, **8 accepted cases**, no rejected
  cases or exact duplicate titles, and a **19,063-byte response** including Excel.
  The synthetic password requirement produced the expected 8-20 limits and
  deterministic BVA values 7, 8, 9, 19, 20, 21. The workbook reopened successfully.
  This is one local manual-input sample, not a hosted latency or accuracy guarantee;
  document timing, repeated runs and provider variability remain to be assessed.
- No Git push, GitHub Actions run, Vercel deployment or public URL has been made.

Do not mark Stage 1 complete until Linux dependency installation, Vercel build,
live timing and the full hosted UI-to-Excel journey have passed.
