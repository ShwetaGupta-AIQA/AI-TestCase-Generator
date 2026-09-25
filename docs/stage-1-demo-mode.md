# Stage 1 - Stateless demo mode

The demo keeps the existing requirement analysis, scenario/test generation,
deterministic QA, BVA, IDs, metrics and Excel export. FastAPI handles generation
within the request; Streamlit holds completed results and workbook bytes in its
session. It needs no database, worker, saved run history or shared disk.

## Run locally

Set `OPENROUTER_API_KEY` in your local `.env` or API process environment. Keep it
out of Git. The model remains configurable with `OPENROUTER_MODEL`.

In one PowerShell terminal, from the project root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.demo:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
$env:TESTGEN_MODE = 'demo'
$env:TESTGEN_API_URL = 'http://127.0.0.1:8000'
.\.venv\Scripts\python.exe -m streamlit run ui/streamlit_app.py
```

Open http://localhost:8501 and use **Load Sample Requirement**. API documentation
is at http://127.0.0.1:8000/docs. `TESTGEN_MODE` selects the UI; the explicit
`api.demo:app` entry point selects the API. Both must match. Merely setting the UI
mode does not change `api.main:app` into the demo API.

The durable local/Compose path remains `api.main:app` plus `runs.worker`, with
`TESTGEN_MODE=durable` (the default). Compose is still configured for that path.

## Request behavior

- `GET /health`: liveness and `mode: demo`; no model call.
- `POST /generate`: JSON `{"requirement":"Password length must be 8 to 20 characters"}`.
- `POST /generate-document`: multipart field `file`, TXT/DOCX/text-based PDF.
- Generation responses contain `results`, processed/extracted counts,
  `excel_base64`, and a demo notice. The UI decodes the workbook for downloading.
- `/runs` and saved run/download routes are absent from this API.
- Responses disable caching. No application run files or database records persist.

Refreshing, reconnecting or restarting can lose a session's results. Download the
workbook before leaving. Keeping the same session through ordinary UI reruns
retains results; changing input clears them. Generation is not automatically
retried, and there is no durable idempotency or resume guarantee. An interrupted
client may leave an in-flight provider request running.

## Demo bounds

| Resource | Limit |
| --- | --- |
| Requirement text | 5-12,000 characters after trimming |
| Uploaded file | 4,000,000 bytes |
| Entire incoming POST body | 4,100,000 bytes, including multipart overhead |
| Extracted document text | 30,000 characters |
| PDF pages | 20 |
| Expanded DOCX archive | 20,000,000 bytes |
| Processed document requirements | First two; actual extracted and processed counts shown |
| Scenarios per requirement | Three |
| Cases per scenario | Three |
| Provider requests per generation | Twelve, including JSON-format retries |
| Concurrent test-case requests | Two scenario requests at a time |
| Completion tokens per provider request | 4,000 |
| Encoded response, including workbook | 4,000,000 bytes |
| Generation time budget | 240 seconds, checked cooperatively |
| Provider I/O timeout | Smaller of 60 seconds and remaining time budget |
| UI HTTP timeout | 260 seconds, 10 seconds to connect |

Excess scenarios/cases cause a readable error, not silent truncation. The first
two document requirements are the existing intentional processing subset.
Limits apply through request-local context and do not restrict durable workflows.
For the public demo, independent test-case requests run in batches of two; final
case IDs, validation, duplicate checks, and Excel rows are still processed in
scenario order.

The deadline is **cooperative**, not process cancellation: checks stop further AI
calls and reject late results, but cannot interrupt arbitrary PDF parsing or an
already running synchronous operation. HTTP timeouts are I/O timeouts, not a hard
wall-clock guarantee. Validate live latency before accepting this for Vercel;
the host's execution limit remains the final ceiling. Parser limits reduce work
but are not a complete sandbox for malicious documents.

## Verification and remaining deployment work

Local verification on 24 September 2026: **74 tests passed**, including 11 new
demo tests; `pip check` passed. The full suite used an isolated SQLite database
for the existing durable-mode tests. Results are in `.tmp/demo-regression.log`.

Automated demo tests use mocked model responses and actual API, document and Excel
code. They cover database-free import, missing history routes, byte/text limits,
request and response size, generation bounds, model-call budgets, deadline errors,
session results and workbook traceability. They do not measure live model accuracy
or cloud runtime performance.

Cloud entry point and dependency configuration are now prepared. See
[cloud setup and outstanding verification](stage-1-cloud-setup.md).
Next: verify Linux installation and live latency, then deploy and test the full
public journey. No public URL is created by enabling this mode locally.
