import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
API_URL = os.getenv("TESTGEN_API_URL", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT = httpx.Timeout(15.0, connect=3.0)


class BackendUnavailable(RuntimeError):
    pass


def _request(method, path, **kwargs):
    try:
        response = httpx.request(method, API_URL + path, timeout=TIMEOUT, **kwargs)
        response.raise_for_status()
        return response
    except httpx.HTTPStatusError as exc:
        detail = "Request failed."
        try:
            detail = exc.response.json().get("detail", detail)
        except ValueError:
            pass
        raise ValueError(detail) from exc
    except httpx.RequestError as exc:
        raise BackendUnavailable("The TestGen API is unavailable. Start the API and worker, then retry.") from exc


def submit_manual(requirement, idempotency_key):
    return _request("POST", "/runs", json={"requirement": requirement,
                                            "idempotency_key": idempotency_key}).json()


def submit_document(filename, content, idempotency_key):
    return _request("POST", "/runs/document", data={"idempotency_key": idempotency_key},
                    files={"file": (filename, content)}).json()


def get_run(run_id):
    return _request("GET", f"/runs/{run_id}").json()


def get_history():
    return _request("GET", "/runs", params={"limit": 20}).json()["runs"]


def download_excel(run_id):
    return _request("GET", f"/runs/{run_id}/download").content
