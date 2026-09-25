import os
import base64
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
API_URL = os.getenv("TESTGEN_API_URL", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT = httpx.Timeout(15.0, connect=3.0)


class BackendUnavailable(RuntimeError):
    pass


def _request(method, path, timeout=TIMEOUT, **kwargs):
    try:
        response = httpx.request(method, API_URL + path, timeout=timeout, **kwargs)
        response.raise_for_status()
        return response
    except httpx.HTTPStatusError as exc:
        detail = "Request failed."
        try:
            detail = exc.response.json().get("detail", detail)
        except ValueError:
            pass
        raise ValueError(detail) from exc
    except httpx.TimeoutException as exc:
        raise BackendUnavailable("The API request timed out. Try a shorter requirement; the request is not automatically retried.") from exc
    except httpx.RequestError as exc:
        raise BackendUnavailable("The TestGen API is unavailable. Check the configured API URL and retry.") from exc


def create_workspace():
    return _request("POST", "/workspaces").json()["workspace_token"]


def _workspace_headers(workspace_token):
    return {"X-TestGen-Workspace": workspace_token} if workspace_token else {}


def demo_mode():
    return os.getenv("TESTGEN_MODE", "durable").lower() == "demo"


def workspace_required():
    return os.getenv("TESTGEN_REQUIRE_WORKSPACE", "false").lower() == "true"


def generate_demo(requirement=None, filename=None, content=None):
    kwargs = ({"files": {"file": (filename, content)}} if filename is not None
              else {"json": {"requirement": requirement}})
    route = "/generate-document" if filename is not None else "/generate"
    response = _request("POST", route, timeout=httpx.Timeout(260.0, connect=10.0), **kwargs)
    try:
        report = response.json()
        report["excel_data"] = base64.b64decode(report.pop("excel_base64"), validate=True)
        return report
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("The API returned an invalid demo report.") from exc


def submit_manual(requirement, idempotency_key, workspace_token=None):
    return _request("POST", "/runs", json={"requirement": requirement,
                                            "idempotency_key": idempotency_key},
                    headers=_workspace_headers(workspace_token)).json()


def submit_document(filename, content, idempotency_key, workspace_token=None):
    return _request("POST", "/runs/document", data={"idempotency_key": idempotency_key},
                    files={"file": (filename, content)},
                    headers=_workspace_headers(workspace_token)).json()


def get_run(run_id, workspace_token=None):
    return _request("GET", f"/runs/{run_id}", headers=_workspace_headers(workspace_token)).json()


def get_history(workspace_token=None):
    return _request("GET", "/runs", params={"limit": 20},
                    headers=_workspace_headers(workspace_token)).json()["runs"]


def download_excel(run_id, workspace_token=None):
    return _request("GET", f"/runs/{run_id}/download", headers=_workspace_headers(workspace_token)).content
