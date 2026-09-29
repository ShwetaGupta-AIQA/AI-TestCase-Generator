"""Run the downloaded suite against a loopback-only mock server."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from zipfile import ZipFile

from models.api_testing import ApiManualRequest
from services.api_spec_parser import manual_contract
from services.api_test_designer import design_api_tests
from services.api_test_exporter import export_pytest_suite


class ExportRunnerTests(unittest.TestCase):
    def test_real_pytest_against_local_mock(self):
        received = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                received.append((self.path, body))
                self.send_response(201)
                self.end_headers()
                self.wfile.write(b'{}')

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            contract = manual_contract(ApiManualRequest(method="POST", path="/items",
                success_status="201", required_body_fields=["name"]))
            plan = design_api_tests(contract, contract.endpoints[0])
            # Scope this check to one valid request and one unconfirmed negative case.
            plan.test_cases = plan.test_cases[:2]
            with tempfile.TemporaryDirectory() as directory:
                with ZipFile(BytesIO(export_pytest_suite(plan))) as archive:
                    Path(directory, "test_api_contract.py").write_bytes(archive.read("test_api_contract.py"))
                environment = dict(os.environ, API_BASE_URL=f"http://127.0.0.1:{server.server_port}",
                                   NO_PROXY="127.0.0.1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
                result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                         "test_api_contract.py"], cwd=directory, env=environment,
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("1 passed, 1 skipped", result.stdout)
            self.assertEqual(received, [("/items", {"name": "sample_name"})])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
