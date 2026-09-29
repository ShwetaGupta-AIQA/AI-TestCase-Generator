import os
import json
from urllib.parse import urlsplit, parse_qs
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from models.api_testing import ApiManualRequest
from services.api_spec_parser import manual_contract
from services.api_test_designer import design_api_tests
from services.api_test_exporter import export_soapui_project


class SoapUiRunnerTests(unittest.TestCase):
    def test_local_request(self):
        home = Path(os.environ.get("SOAPUI_HOME", r"D:\Softwares\SoapUI-5.10.0"))
        if not home.exists():
            self.skipTest("Set SOAPUI_HOME to run SoapUI integration")
        received = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append((self.path, self.headers.get('X-Test'), self.rfile.read(int(self.headers.get('Content-Length', 0)))))
                self.send_response(201)
                self.end_headers()
                self.wfile.write(b'{}')
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            contract = manual_contract(ApiManualRequest(method='POST', path='/items', success_status='201',
                required_body_fields=['name'], base_url=f'http://127.0.0.1:{server.server_port}'))
            plan = design_api_tests(contract, contract.endpoints[0])
            plan.test_cases = plan.test_cases[:1]
            plan.endpoint.path = '/items/{id}'
            plan.test_cases[0].path = '/items/123'
            plan.test_cases[0].path_params = {'id': '123'}
            plan.test_cases[0].query_params = {'search': 'a & b'}
            plan.test_cases[0].request_headers = {'X-Test': 'header-value'}
            with tempfile.TemporaryDirectory() as temp:
                project = Path(temp, 'project.xml')
                project.write_bytes(export_soapui_project(plan))
                result = subprocess.run([str(home / 'jre/bin/java.exe'), '-Djava.awt.headless=true',
                    '-cp', str(home / 'bin/soapui-5.10.0.jar') + ';' + str(home / 'lib/*'),
                    'com.eviware.soapui.tools.SoapUITestCaseRunner', '-r', str(project)],
                    cwd=temp, capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, (result.stdout + result.stderr)[-10000:])
                plan.test_cases[0].expected_status = '202'
                project.write_bytes(export_soapui_project(plan))
                failed = subprocess.run([str(home / 'jre/bin/java.exe'), '-Djava.awt.headless=true',
                    '-cp', str(home / 'bin/soapui-5.10.0.jar') + ';' + str(home / 'lib/*'),
                    'com.eviware.soapui.tools.SoapUITestCaseRunner', '-r', str(project)],
                    cwd=temp, capture_output=True, text=True, timeout=60)
                self.assertNotEqual(failed.returncode, 0)
                self.assertIn('FAILED', failed.stdout + failed.stderr)
            self.assertEqual(len(received), 2)
            for path, header, body in received:
                self.assertEqual(urlsplit(path).path, '/items/123')
                self.assertEqual(parse_qs(urlsplit(path).query), {'search': ['a & b']})
                self.assertEqual(header, 'header-value')
                self.assertEqual(json.loads(body), {'name': 'sample_name'})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)
