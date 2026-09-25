import json
from datetime import timedelta
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update

from api.main import app
from runs.database import SessionLocal, init_database
from runs.models import GenerationRun, utcnow
from runs.repository import (claim_next_run, create_run, fail_stale_runs, finish_run,
                             get_run, heartbeat, list_runs, serialize)
from runs.worker import process_one


class DurableRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_database()

    def key(self):
        return f"test-{uuid4()}"

    def setUp(self):
        # Keep earlier test-created jobs from being claimed by this test's worker.
        with SessionLocal.begin() as session:
            session.execute(update(GenerationRun).where(GenerationRun.status == "queued").values(
                status="failed", stage="Test cleanup", completed_at=utcnow()))

    def tearDown(self):
        # Tests use the local database by default; remove only rows this class owns.
        with SessionLocal.begin() as session:
            run_ids = list(session.scalars(select(GenerationRun.id).where(
                GenerationRun.idempotency_key.like("test-%"))))
            session.execute(delete(GenerationRun).where(
                GenerationRun.idempotency_key.like("test-%")))
        for run_id in run_ids:
            directory = Path(__file__).resolve().parents[1] / "output" / "runs" / run_id
            for name in ("source.txt", "source.docx", "source.pdf", "TestGen_Output.xlsx"):
                (directory / name).unlink(missing_ok=True)
            try:
                directory.rmdir()
            except OSError:
                pass

    def test_idempotent_submit_and_payload_conflict(self):
        key = self.key()
        first, created = create_run(idempotency_key=key, input_type="manual", input_text="Requirement alpha")
        second, repeated = create_run(idempotency_key=key, input_type="manual", input_text="Requirement alpha")
        self.assertTrue(created)
        self.assertFalse(repeated)
        self.assertEqual(first.id, second.id)
        with self.assertRaises(ValueError):
            create_run(idempotency_key=key, input_type="manual", input_text="Different requirement")

        document_key = self.key()
        create_run(idempotency_key=document_key, input_type="document", filename="requirements.txt", content=b"same")
        with self.assertRaises(ValueError):
            create_run(idempotency_key=document_key, input_type="document", filename="requirements.pdf", content=b"same")

    def test_workspace_owner_cannot_read_another_workspace_run(self):
        owner_a, owner_b = str(uuid4()), str(uuid4())
        first, _ = create_run(idempotency_key=self.key(), input_type="manual",
                              input_text="Requirement alpha", owner_id=owner_a)
        second, _ = create_run(idempotency_key=self.key(), input_type="manual",
                               input_text="Requirement beta", owner_id=owner_b)
        self.assertIsNotNone(get_run(first.id, owner_id=owner_a))
        self.assertIsNone(get_run(first.id, owner_id=owner_b))
        self.assertEqual([run.id for run in list_runs(owner_id=owner_a)], [first.id])
        self.assertEqual([run.id for run in list_runs(owner_id=owner_b)], [second.id])

    def test_worker_persists_result_and_excel_without_model_on_restore(self):
        run, _ = create_run(idempotency_key=self.key(), input_type="manual", input_text="Password length 8 to 20")
        report = {"results": [], "extracted_count": 1, "processed_count": 1}

        def fake_generate(requirement, output_path):
            Path(output_path).write_bytes(b"PK workbook")
            return report

        with patch("runs.worker.generate_manual_to_file", side_effect=fake_generate):
            self.assertTrue(process_one())
        restored = get_run(run.id)
        self.assertEqual(restored.status, "completed")
        self.assertEqual(json.loads(restored.result_json), report)
        self.assertEqual(Path(restored.excel_path).read_bytes(), b"PK workbook")
        with patch("runs.worker.generate_manual_to_file") as model_path:
            self.assertEqual(serialize(restored, include_result=True)["result"], report)
            model_path.assert_not_called()

    def test_stale_claim_is_failed_and_old_owner_cannot_finish(self):
        run, _ = create_run(idempotency_key=self.key(), input_type="manual", input_text="A valid requirement")
        claimed, token = claim_next_run()
        self.assertEqual(claimed.id, run.id)
        self.assertTrue(heartbeat(run.id, token))
        with SessionLocal.begin() as session:
            session.execute(update(GenerationRun).where(GenerationRun.id == run.id).values(
                updated_at=utcnow() - timedelta(minutes=31)))
        self.assertGreaterEqual(fail_stale_runs(30), 1)
        self.assertEqual(get_run(run.id).status, "failed")
        self.assertFalse(finish_run(run.id, token, {"results": []}, "wrong.xlsx"))
        self.assertEqual(get_run(run.id).status, "failed")

    def test_run_api_uuid_status_and_download(self):
        key = self.key()
        with TestClient(app) as client:
            response = client.post("/runs", json={"requirement": "A valid requirement", "idempotency_key": key})
            self.assertEqual(response.status_code, 202)
            run_id = response.json()["run_id"]
            self.assertEqual(client.get(f"/runs/{run_id}").json()["status"], "queued")
            self.assertEqual(client.get("/runs/not-a-uuid").status_code, 404)
            conflict = client.post("/runs", json={"requirement": "Different valid input", "idempotency_key": key})
            self.assertEqual(conflict.status_code, 409)


if __name__ == "__main__":
    unittest.main()
