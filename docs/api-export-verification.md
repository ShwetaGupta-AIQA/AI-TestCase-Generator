# API export verification

## Local evidence

- API tests cover contract parsing, review, selection and export contents.
- Streamlit AppTest covers editors and selection, using mocked export responses.
- Exported Python functions are tested with a mocked HTTP transport.
- The actual Pytest runner executes a generated suite against a loopback mock:
  one successful request and one skipped unconfirmed case.

## Before release

SoapUI 5.10.0 runner check: a generated POST project loads and sends its JSON body
to a loopback mock with a 201 status assertion. Fixed missing request endpoint/body
children in REST test steps. Extended runner checks verify headers, encoded query
parameters, path substitution and failure for an incorrect expected status.
Desktop import remains unverified.

- Import Postman collection; set collection variable `base_url` to a test server.
- Confirm JSON Content-Type, query encoding, body and reviewed status assertion.
- Run in Postman Collection Runner; confirm unconfirmed cases send no request.
- Import a fresh SoapUI XML and run one request against a mock.
  The command-line runner is verified for the cases above; desktop review is pending.
- Do not describe Postman execution or broad SoapUI compatibility as verified.
- Rebuild backend and Streamlit dependencies (PyYAML and jsonschema added).
- Deploy backend before UI, then verify OpenAPI JSON/YAML/URL and HTML imports.
- Verify edited expectations and selected cases survive reruns and reach exports.

Generated status assertions do not verify schema, business rules, database state,
idempotency, or performance. Coverage counts are design counts, not execution results.

Postman skip behavior follows:
https://learning.postman.com/latest-v-12/docs/tests-and-scripts/write-scripts/postman-sandbox-reference/pm-execution
