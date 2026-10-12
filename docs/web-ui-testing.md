# Web UI Testing Roadmap

Web UI Testing is a separate workflow from API contract test design. Phases 1
and 2 provide static and opt-in rendered inspection; generated tests are drafts
and TestGen does not execute them.

## Phase 1: Static-page drafts

Implemented in the durable FastAPI mode:

- Inspect one public HTTPS page on port 443. Private/local DNS results and
  redirects are rejected; the HTML response is capped at 1 MiB.
- Extract the document title, description, headings and named interactive
  controls from static HTML. Scripts are ignored, so JavaScript-rendered content
  may be absent.
- Generate structured browser-test drafts from the page summary and a user goal.
  Proposed element locators must match observed controls, and actions are limited
  to click, fill, check, uncheck and select-option operations.
- Review each draft, edit its title/objective, exclude unwanted cases and export
  a Playwright pytest ZIP. Exported tests are not run by the hosted service.

This workflow requires the regular `api.main:app` service and an available model
provider. It is not exposed by the stateless `api.demo:app` adapter. Do not enter
secrets or personal data into page goals; use only pages and environments you are
authorized to inspect and test.

## Phase 2: Rendered-page inspection

Implemented as an opt-in Chromium mode in the durable FastAPI service:

- Select **Render JavaScript** in the Web UI Testing workspace. Set
  `TESTGEN_ENABLE_RENDERED_INSPECTION=true` on the API; it is disabled by default.
- Install Playwright and its Chromium browser locally with
  `python -m pip install -r requirements.txt` and
  `python -m playwright install chromium`. The project Dockerfile installs the
  browser and its OS dependencies during image build.
- Chromium uses a pinned, verified public IPv4 for the initial hostname. Routing
  allows only same-origin HTTPS requests on port 443; cross-origin assets,
  redirects to other hosts, WebSockets, downloads and service workers are blocked.
- Navigation is capped at 15 seconds, followed by a short render-settle interval.
  At most 80 same-origin requests are considered; images, media, fonts and other
  unneeded resource classes are blocked. The snapshot includes visible rendered
  headings and named controls, not screenshots or page source.
- Authentication and user-provided browser state remain unsupported.

The browser runs as a separate Chromium process but is not yet a separate
container or network namespace. Request interception and DNS pinning reduce the
request surface; deployments that inspect untrusted URLs should additionally
enforce outbound network restrictions at the container/host firewall.

## Phase 3: User-controlled execution

- Provide an opt-in local runner or separately deployed isolated runner; do not
  execute arbitrary generated browser code inside the public API process.
- Require explicit target confirmation and a permitted test environment.
- Capture per-step outcomes, screenshots and Playwright traces, and distinguish
  generated assertions from assertions that actually ran.
- Add repeatable mock-site tests for forms, navigation, validation and responsive
  layouts before broader execution support.

## Phase 4: Reusable journeys and integrations

- Support requirement-linked journeys, reusable reviewed locators and richer
  setup/teardown data.
- Consider authenticated test profiles, CI artifacts and issue/test-management
  integrations only after the local execution and secret-handling model is set.
- Evaluate locator stability, assertion quality and execution success separately;
  do not treat those metrics as general model accuracy.