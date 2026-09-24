# Release checklist

## Verified locally

- Existing dependency environment passes `python -m pip check`.
- Automated regression tests cover API routes, document readers, generation with
  mocked AI responses, QA/BVA, metrics, Excel traceability and Streamlit interaction.
- Secret/output exclusions and a placeholder-only `.env.example` are present.

## Still to verify before publishing V1

- Install Git and Docker Desktop; neither was available during packaging.
- Build and run the Docker image; the Dockerfile uses Python 3.14 to match the
  environment used for regression tests. A frozen Windows environment still needs
  verification in Linux, including package/wheel availability.
- Run live generation and `run_evaluation.py` with your own API key. Record results;
  never substitute mocked test results for model accuracy.
- Capture actual screenshots using the synthetic sample BRD (see images/README.md).
- Choose the GitHub repository URL and publish after reviewing staged files.

## Docker verification

```powershell
docker build -t testgen-ai .
docker run --rm --name testgen-ai -p 127.0.0.1:8501:8501 --env-file .env testgen-ai
```

Open http://localhost:8501, generate tests from `sample_documents/login_brd.txt`,
download the workbook and inspect all four sheets. In a second terminal, check
`docker inspect --format='{{.State.Health.Status}}' testgen-ai`.

The default image runs Streamlit. To run the API instead:

```powershell
docker run --rm -p 127.0.0.1:8000:8000 --env-file .env --no-healthcheck testgen-ai python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Check `/health` manually for this API command. The default container health check
targets Streamlit and is disabled when running FastAPI instead.

## GitHub publication

Run from the project root after Git is installed:

```powershell
git init -b main
git check-ignore .env
git add .
git diff --cached --name-only
git diff --cached --stat
```

Confirm `.env`, `.venv`, generated workbooks and proprietary documents are absent.
Review staged changes locally before committing. Configure your Git author identity
if needed, then:

```powershell
git commit -m "Build TestGen AI MVP"
git remote add origin YOUR_ACTUAL_REPOSITORY_URL
git push -u origin main
```

Replace the URL only with the destination you intend to publish to. Do not
force-push an existing repository. If `.env` was previously tracked, ignore rules
alone do not remove it from history: revoke any exposed key before publication.

Suggested description: AI-assisted requirement analysis, test generation, validation,
evaluation and Excel traceability for quality engineering workflows.
