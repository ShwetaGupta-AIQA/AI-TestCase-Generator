import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
from models.api_testing import ApiManualRequest
from services.api_spec_parser import manual_contract
from services.api_test_designer import design_api_tests
from services.api_test_exporter import export_postman_collection


class PostmanRunnerTests(unittest.TestCase):
    def test_generated_collection(self):
        cli = Path(os.environ.get('POSTMAN_CLI', '.tmp/postman-cli/postman-cli.exe')).resolve()
        if not cli.exists():
            self.skipTest('Set POSTMAN_CLI to the official runner')
        received = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append((self.path, self.headers.get('X-Test'), json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                self.send_response(201)
                self.end_headers()
                self.wfile.write(b'{}')
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            contract = manual_contract(ApiManualRequest(method='POST', path='/items', success_status='201', required_body_fields=['name']))
            plan = design_api_tests(contract, contract.endpoints[0])
            plan.base_url = f'http://127.0.0.1:{server.server_port}'
            plan.test_cases = plan.test_cases[:2]
            plan.test_cases[0].request_headers = {'X-Test': 'sample'}
            plan.test_cases[0].query_params = {'search': 'a & b'}
            with tempfile.TemporaryDirectory() as temp:
                collection = Path(temp, 'collection.json')
                for expected, succeeds in [('201', True), ('202', False)]:
                    plan.test_cases[0].expected_status = expected
                    collection.write_bytes(export_postman_collection(plan))
                    result = subprocess.run([str(cli), 'collection', 'run', str(collection)], cwd=temp,
                        capture_output=True, text=True, timeout=60)
                    self.assertEqual(result.returncode == 0, succeeds, (result.stdout + result.stderr)[-6000:])
            self.assertEqual(len(received), 2, 'Unconfirmed cases must not send requests')
            for path, header, body in received:
                self.assertEqual(urlsplit(path).path, '/items')
                self.assertEqual(parse_qs(urlsplit(path).query), {'search': ['a & b']})
                self.assertEqual(header, 'sample')
                self.assertEqual(body, {'name': 'sample_name'})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)
