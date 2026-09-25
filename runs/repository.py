import json
import hashlib
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from runs.database import SessionLocal, init_database
from runs.models import GenerationRun, utcnow

RUNS_ROOT = Path(__file__).resolve().parents[1] / "output/runs"
PUBLIC_ERROR = "Generation failed. Check the document and API configuration, then retry."


def valid_run_id(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def run_directory(run_id):
    run_id = valid_run_id(run_id)
    if not run_id:
        raise ValueError("Invalid run ID.")
    return RUNS_ROOT / run_id


def serialize(run, include_result=False):
    data = {
        "run_id": run.id, "status": run.status, "stage": run.stage,
        "input_type": run.input_type, "original_filename": run.original_filename,
        "error": run.error_message, "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
    }
    if include_result and run.result_json:
        data["result"] = json.loads(run.result_json)
    data["excel_available"] = bool(run.excel_data) or bool(run.excel_path and Path(run.excel_path).is_file())
    return data


def create_run(*, idempotency_key, input_type, input_text=None, filename=None, content=None, owner_id="local"):
    init_database()
    normalized_key = idempotency_key.strip()
    if not normalized_key or len(normalized_key) > 128:
        raise ValueError("Idempotency key must contain 1 to 128 characters.")
    suffix = Path(filename or "").suffix.lower()
    material = content if content is not None else (input_text or "").encode()
    fingerprint = hashlib.sha256(input_type.encode() + b"\0" + suffix.encode() + b"\0" + material).hexdigest()
    with SessionLocal() as session:
        existing = session.scalar(select(GenerationRun).where(
            GenerationRun.idempotency_key == normalized_key, GenerationRun.owner_id == owner_id))
        if existing:
            if existing.input_fingerprint != fingerprint or existing.input_type != input_type:
                raise ValueError("This idempotency key was already used for different input.")
            return existing, False
        run_id = str(uuid4())
        # Uploaded bytes live in the database. The worker materializes them in
        # its own temporary directory, so API and worker services do not need a
        # shared disk in the cloud.
        source_path = None
        run = GenerationRun(id=run_id, owner_id=owner_id, idempotency_key=normalized_key, input_fingerprint=fingerprint,
                            input_type=input_type,
                            input_text=input_text, original_filename=filename, source_path=source_path,
                            source_data=content)
        session.add(run)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            existing = session.scalar(select(GenerationRun).where(
                GenerationRun.idempotency_key == normalized_key, GenerationRun.owner_id == owner_id))
            if existing:
                if existing.input_fingerprint != fingerprint or existing.input_type != input_type:
                    raise ValueError("This idempotency key was already used for different input.")
                return existing, False
            raise
        return run, True


def get_run(run_id, owner_id=None):
    run_id = valid_run_id(run_id)
    if not run_id:
        return None
    with SessionLocal() as session:
        run = session.get(GenerationRun, run_id)
        return run if run and (owner_id is None or run.owner_id == owner_id) else None


def list_runs(limit=20, owner_id=None):
    with SessionLocal() as session:
        statement = select(GenerationRun)
        if owner_id is not None:
            statement = statement.where(GenerationRun.owner_id == owner_id)
        return list(session.scalars(statement.order_by(GenerationRun.created_at.desc()).limit(limit)))


def claim_next_run():
    """Claim one queued row. The conditional update prevents two workers owning it."""
    init_database()
    with SessionLocal.begin() as session:
        candidate = session.scalar(select(GenerationRun.id).where(GenerationRun.status == "queued")
                                   .order_by(GenerationRun.created_at).limit(1))
        if not candidate:
            return None
        now = utcnow()
        worker_token = str(uuid4())
        changed = session.execute(update(GenerationRun).where(
            GenerationRun.id == candidate, GenerationRun.status == "queued").values(
                status="running", stage="Starting generation", started_at=now,
                updated_at=now, attempts=GenerationRun.attempts + 1, worker_token=worker_token))
        if changed.rowcount != 1:
            return None
    return get_run(candidate), worker_token


def heartbeat(run_id, worker_token):
    with SessionLocal.begin() as session:
        result = session.execute(update(GenerationRun).where(
            GenerationRun.id == run_id, GenerationRun.status == "running",
            GenerationRun.worker_token == worker_token).values(updated_at=utcnow()))
        return result.rowcount == 1


def finish_run(run_id, worker_token, result, excel_path):
    now = utcnow()
    workbook = Path(excel_path)
    excel_data = workbook.read_bytes() if workbook.is_file() else None
    with SessionLocal.begin() as session:
        result = session.execute(update(GenerationRun).where(
            GenerationRun.id == run_id, GenerationRun.status == "running",
            GenerationRun.worker_token == worker_token).values(
            status="completed", stage="Completed", result_json=json.dumps(result, ensure_ascii=False),
            excel_path=str(excel_path), excel_data=excel_data, error_message=None, completed_at=now, updated_at=now,
            worker_token=None))
        return result.rowcount == 1


def fail_run(run_id, worker_token, message=PUBLIC_ERROR):
    now = utcnow()
    with SessionLocal.begin() as session:
        result = session.execute(update(GenerationRun).where(
            GenerationRun.id == run_id, GenerationRun.status == "running",
            GenerationRun.worker_token == worker_token).values(
            status="failed", stage="Failed", error_message=message, completed_at=now,
            updated_at=now, worker_token=None))
        return result.rowcount == 1


def fail_stale_runs(minutes=30):
    init_database()
    cutoff = utcnow() - timedelta(minutes=minutes)
    with SessionLocal.begin() as session:
        result = session.execute(update(GenerationRun).where(
            GenerationRun.status == "running", GenerationRun.updated_at < cutoff).values(
                status="failed", stage="Worker interrupted", error_message=(
                    "The worker stopped before this run completed. Submit a new run to retry safely."),
                completed_at=utcnow(), updated_at=utcnow(), worker_token=None))
        return result.rowcount
