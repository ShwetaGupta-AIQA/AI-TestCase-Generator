# Stage 2 — Free-tier durable deployment

Stage 2 changes the project from the public, session-only demonstration into a
small persistent portfolio application. It continues to use the Streamlit UI,
but uses one free Render web service and a free Render Postgres database for
the durable workflow.

## Why the API moves from Vercel

The current Vercel deployment remains the Stage 1 demo API. Its free function
duration is unsuitable for this workload: a verified live generation can take
more than one minute. The durable workflow uses a worker and must outlive an
HTTP request, so it is deployed to Render instead. Render currently offers a
free web service and Postgres with free-tier limits. The image starts FastAPI
and the database-backed worker together because a separate worker service is
not available on the free plan.
Check current terms before deploying: [Render pricing](https://render.com/pricing),
[Render free-tier limits](https://render.com/docs/free), and
[Vercel function limits](https://vercel.com/docs/functions/limitations).

## What is implemented

- PostgreSQL-backed run history, result JSON, uploaded document bytes, and Excel
  workbook bytes. API and worker no longer need a shared filesystem.
- An API-issued, signed anonymous workspace token. A run, its status, history,
  and workbook download are visible only to the workspace that created it.
- A Streamlit session obtains and sends the opaque workspace token automatically.
- `render.yaml` defines the free API service and Postgres database.
- Existing local durable mode remains available without workspace protection.

This is anonymous workspace isolation, not an email/password account system.
Closing a browser session creates a new workspace; Stage 3 can replace it with
Supabase Auth or another identity provider if real accounts are needed.

## Deployment steps

1. In Render, create a **Blueprint** from this GitHub repository and select
   `render.yaml`.
2. On the web service, set `OPENROUTER_API_KEY` and leave
   `OPENROUTER_MODEL=openrouter/free` initially.
3. Confirm the web service has `TESTGEN_REQUIRE_WORKSPACE=true` and a generated
   `TESTGEN_WORKSPACE_SECRET` of at least 32 characters.
4. Wait for the database and API health checks to become healthy. The API image
   starts the worker automatically.
5. In Streamlit Community Cloud, change secrets from Stage 1 demo mode to:

   ```toml
   TESTGEN_MODE = "durable"
   TESTGEN_REQUIRE_WORKSPACE = "true"
   TESTGEN_API_URL = "https://YOUR-RENDER-WEB-SERVICE.onrender.com"
   ```

   The OpenRouter key and workspace secret belong only on Render, never in
   Streamlit secrets or GitHub.
6. Test a manual run: submit it, refresh while it is queued/running, reopen it
   from **Saved runs**, then download its workbook. Repeat with a TXT upload.

## Free-tier operating limits

- Free services can sleep and have usage limits; the first request may be slow.
- Render's free Postgres database currently has a 1 GB storage limit and expires
  after 30 days. Treat Stage 2 data as disposable and recreate/export it before
  expiry; permanent durable storage requires a later paid or different provider
  decision.
- The free model provider can be slow or unavailable. The app handles a failed
  run but does not auto-retry model calls because a retry can consume quota.
- Store only nonconfidential requirements. Run data and files are persisted in
  Postgres until a future retention/delete feature is added.
- Stage 1’s Vercel + Streamlit demo remains useful as the no-sign-in public
  showcase. Switch Streamlit to Stage 2 only after the durable Render journey
  has passed.
