# React screenshot capture guide

[architecture.png](architecture.png) is the current React architecture, exported from the checked Archify HTML diagram. It replaces the older preview.

Four current captures are published: [Generate Tests](01-react-workspace.png), [API Testing](03-api-testing.png), [Web UI Testing](04-web-testing.png), and [Run History](05-run-history.png). They show the actual local React interface with fictional inputs. History records are synthetic; API test design uses the local backend. No AI-provider calls were made. Generated-results and Excel screenshots listed below remain future captures.

Capture the React app at http://127.0.0.1:5173 using fictional inputs. Do not use old Streamlit screens as React previews.

| Filename | What to show |
| --- | --- |
| `01-react-workspace.png` | Generate Tests, navigation, sample requirement |
| `02-generated-results.png` | Completed analysis, scenarios, cases, workbook download |
| `03-api-testing.png` | Sample endpoint, reviewed cases, expected statuses, exports |
| `04-web-testing.png` | Observed controls, reviewed drafts, Playwright export |
| `05-run-history.png` | Saved generation jobs and reopening results |
| `06-excel-traceability.png` | Actual exported Traceability sheet |

Use the password-length example or `sample_documents/login_brd.txt`. Prefer a consistent light theme and roughly 1440 x 900 captures with readable text.

Exclude provider keys, recovery tokens, personal paths, and private documents. Label mock-backed results accurately; they do not prove real-provider quality. Add README image links only after real captures exist. See [interactive diagrams](../diagrams/README.md) for architecture exports.
