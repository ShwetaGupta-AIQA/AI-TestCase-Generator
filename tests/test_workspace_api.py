import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from api.main import app


class WorkspaceApiTests(unittest.TestCase):
    def test_workspace_protects_saved_run_routes(self):
        environment = {
            "TESTGEN_REQUIRE_WORKSPACE": "true",
            "TESTGEN_WORKSPACE_SECRET": "x" * 32,
        }
        with patch.dict(os.environ, environment, clear=False), TestClient(app) as client:
            first = client.post("/workspaces")
            second = client.post("/workspaces")
            self.assertEqual(first.status_code, 201)
            token_a = first.json()["workspace_token"]
            token_b = second.json()["workspace_token"]
            created = client.post("/runs", headers={"X-TestGen-Workspace": token_a}, json={
                "requirement": "A valid requirement", "idempotency_key": f"test-{uuid4()}"})
            self.assertEqual(created.status_code, 202)
            run_id = created.json()["run_id"]
            self.assertEqual(client.get("/runs").status_code, 401)
            self.assertEqual(client.get(f"/runs/{run_id}", headers={"X-TestGen-Workspace": token_b}).status_code, 404)
            self.assertEqual(client.get(f"/runs/{run_id}", headers={"X-TestGen-Workspace": token_a}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
