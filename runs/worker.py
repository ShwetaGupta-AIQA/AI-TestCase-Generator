"""Database-backed worker. Run with: python -m runs.worker"""
import argparse
import logging
import os
import time
import tempfile
from threading import Event, Thread
from pathlib import Path

from document_pipeline import run_document_pipeline
from ui.workflow import generate_manual_to_file
from runs.repository import (claim_next_run, fail_run, fail_stale_runs, finish_run,
                             heartbeat, run_directory)
from services.generation_errors import generation_error_message
from services.provider_errors import provider_error_message
from openai import APIError

log = logging.getLogger("testgen.worker")


def process_one():
    claim = claim_next_run()
    if claim is None:
        return False
    run, worker_token = claim
    stopped = Event()
    interval = max(2, int(os.getenv("WORKER_HEARTBEAT_SECONDS", "10")))
    def maintain_lease():
        while not stopped.wait(interval):
            if not heartbeat(run.id, worker_token):
                return
    thread = Thread(target=maintain_lease, daemon=True)
    thread.start()
    try:
        directory = run_directory(run.id)
        directory.mkdir(parents=True, exist_ok=True)
        excel_path = directory / "TestGen_Output.xlsx"
        if run.input_type == "document":
            # Stage 2 stores the upload in Postgres so a separately hosted
            # worker does not need the API service's filesystem or a disk.
            if run.source_data is not None:
                suffix = Path(run.original_filename or "document.txt").suffix or ".txt"
                with tempfile.TemporaryDirectory(prefix="testgen-run-") as temporary:
                    source = Path(temporary) / f"source{suffix}"
                    source.write_bytes(run.source_data)
                    report = run_document_pipeline(source, excel_path)
            else:
                report = run_document_pipeline(Path(run.source_path), excel_path)
            report.pop("output_file", None)
        else:
            report = generate_manual_to_file(run.input_text, excel_path)
        finish_run(run.id, worker_token, report, excel_path)
    except APIError as exc:
        log.error("Run %s failed with provider error", run.id)
        fail_run(run.id, worker_token, provider_error_message(exc))
    except (ValueError, OSError) as exc:
        log.error("Run %s failed during generation", run.id)
        fail_run(run.id, worker_token, generation_error_message(exc))
    except Exception:
        log.error("Run %s failed unexpectedly", run.id)
        fail_run(run.id, worker_token)
    finally:
        stopped.set()
        thread.join(timeout=1)
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Process at most one queued run")
    parser.add_argument("--poll-seconds", type=float, default=float(os.getenv("WORKER_POLL_SECONDS", "2")))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    fail_stale_runs(int(os.getenv("WORKER_STALE_MINUTES", "30")))
    last_sweep = time.monotonic()
    while True:
        processed = process_one()
        if time.monotonic() - last_sweep >= 60:
            fail_stale_runs(int(os.getenv("WORKER_STALE_MINUTES", "30")))
            last_sweep = time.monotonic()
        if args.once:
            return 0
        if not processed:
            time.sleep(max(0.2, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
