# TestGen AI System Architecture

TestGen AI has three related runtime paths: queued requirement generation,
bounded session-only demo generation, and synchronous API test design/export.

```mermaid
flowchart TB
    User[User] --> UI[Streamlit workspace]

    subgraph Durable[Durable requirement generation]
        UI -->|Submit job, poll status, view history, download workbook| API[FastAPI: api.main]
        API -->|Queue job, read results| DB[(SQLite locally / PostgreSQL on Render)]
        DB -->|Claim queued job| Worker[Generation worker: runs.worker]
        Worker -->|Manual requirement| Pipeline[Requirement pipeline]
        Worker -->|Uploaded document| Reader[Document reader and requirement extraction]
        Reader --> Pipeline
        Pipeline -->|Analyze, create scenarios and test content| LLM[OpenRouter model]
        Pipeline --> QA[Deterministic QA and evaluation]
        QA -->|IDs, BVA, validation, metrics| Worker
        Worker -->|Save report and workbook bytes| DB
        API -->|Status, results, history, workbook| UI
    end

    subgraph Demo[Stateless public demo]
        UI -->|Demo mode| DemoAPI[Separate FastAPI app: api.demo]
        DemoAPI -->|In-request generation| DemoFlow[ui.workflow]
        DemoFlow -->|Requirement understanding and test content| LLM
        DemoAPI -->|Bounded report and workbook response| UI
    end

    subgraph APITests[API test design and export]
        UI -->|Manual details, OpenAPI or HTML docs| API
        Docs[Optional public API specification or documentation URL] --> Parser[Contract parsers]
        API --> Parser
        Parser --> Designer[Deterministic API test designer]
        Designer --> Exporters[Excel, Postman, Pytest or SoapUI exporters]
        Exporters -->|Download; design only, not execution| UI
        UI -->|User runs selected assets| Runner[Local test runner]
        Runner --> Target[Mock, local, test or staging API]
    end
```

## Runtime Paths

### Durable requirement generation

The default workspace submits manual or document jobs to FastAPI. The API stores
queued jobs in the configured database; a separate worker claims them, runs the
generation pipeline, and saves the report and workbook bytes. The UI polls the
API for status and retrieves completed results. Local development defaults to
SQLite; the Render deployment uses PostgreSQL. Uploaded document bytes are stored
with the run so the worker does not depend on a shared filesystem.

### Stateless demo

The public demo uses the separate `api.demo:app` application. It calls the
generation workflow during the request and returns session-only results. It does
not use the durable run database or worker, and applies request, size, time and
generation limits.

### API test design and export

Manual endpoint details, OpenAPI documents and HTML API documentation are parsed
into an API contract. The designer creates deterministic test plans; this path
does not call the LLM. Exporters produce files for review and user-directed
execution. TestGen does not execute those exported tests against a target API.

## LLM and Deterministic Responsibilities

The LLM supports requirement understanding, scenario generation and test-case
content generation. Python code assigns IDs, calculates supported boundary values,
validates generated cases, evaluates quality metrics, parses API contracts and
designs API test plans. Structural and deterministic checks do not guarantee
semantic correctness or complete test coverage.

## Workspace Protection

The Render deployment enables signed anonymous workspace tokens to scope access
to saved runs. Local development defaults to trusted mode unless
`TESTGEN_REQUIRE_WORKSPACE=true` is set. These tokens do not provide user accounts
or a full identity provider.

