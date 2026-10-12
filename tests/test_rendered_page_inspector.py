import sys
import types
import unittest
from unittest.mock import Mock, patch

from services.rendered_page_inspector import (
    ALLOWED_RESOURCE_TYPES,
    MAX_PAGE_REQUESTS,
    _same_https_origin,
    _render_request_allowed,
    inspect_rendered_public_page,
    rendered_inspection_enabled,
)


class FakeRoute:
    def __init__(self, url):
        self.request = types.SimpleNamespace(url=url)
        self.continued = False
        self.abort_reason = ""

    def continue_(self):
        self.continued = True

    def abort(self, reason):
        self.abort_reason = reason


class RenderedPageInspectorTests(unittest.TestCase):
    def test_same_origin_policy_requires_https_same_host_and_standard_port(self):
        self.assertTrue(_same_https_origin("https://example.com/next", "example.com"))
        self.assertFalse(_same_https_origin("https://cdn.example.com/app.js", "example.com"))
        self.assertFalse(_same_https_origin("https://example.com:444/app.js", "example.com"))
        self.assertFalse(_same_https_origin("http://example.com/app.js", "example.com"))
        self.assertFalse(_same_https_origin("https://user@example.com/", "example.com"))

    def test_request_policy_caps_count_and_blocks_heavy_or_external_resources(self):
        self.assertTrue(_render_request_allowed("https://example.com/app.js", "example.com", "script", 1))
        self.assertFalse(_render_request_allowed("https://example.com/photo.png", "example.com", "image", 1))
        self.assertFalse(_render_request_allowed("https://cdn.example.net/app.js", "example.com", "script", 1))
        self.assertFalse(_render_request_allowed("https://example.com/app.js", "example.com", "script", MAX_PAGE_REQUESTS + 1))
        self.assertIn("document", ALLOWED_RESOURCE_TYPES)

    @patch.dict("os.environ", {"TESTGEN_ENABLE_RENDERED_INSPECTION": "true"})
    def test_rendered_inspection_is_explicitly_opt_in(self):
        self.assertTrue(rendered_inspection_enabled())

    @patch("services.rendered_page_inspector.socket.getaddrinfo")
    def test_rendered_inspection_rejects_private_dns_before_browser_import(self, resolve):
        resolve.return_value = [(2, 1, 6, "", ("10.0.0.8", 443))]
        with self.assertRaisesRegex(ValueError, "public IPv4"):
            inspect_rendered_public_page("https://example.com")

    def test_rendered_inspection_pins_dns_and_blocks_cross_origin_requests(self):
        summary = {
            "title": "Rendered Sign In",
            "description": "Sign in to your account",
            "headings": ["Sign in"],
            "elements": [
                {"role": "textbox", "name": "Email", "locator_strategy": "role"},
                {"role": "button", "name": "Continue", "locator_strategy": "role"},
            ],
        }
        requests = []

        class FakePage:
            url = "https://example.com/login"

            def goto(self, url, **kwargs):
                self.goto_args = (url, kwargs)
                for request_url in [url, "https://cdn.example.net/app.js", "http://127.0.0.1/admin"]:
                    route = FakeRoute(request_url)
                    route.request.resource_type = "document" if request_url == url else "script"
                    context.route_handler(route)
                    requests.append(route)
                return types.SimpleNamespace(status=200)

            def wait_for_timeout(self, delay):
                self.wait_delay = delay

            def evaluate(self, script):
                self.evaluate_script = script
                return summary

        class FakeContext:
            def route(self, pattern, handler):
                self.route_handler = handler
                context.route_handler = handler

            def route_web_socket(self, pattern, handler):
                websocket = types.SimpleNamespace(close=Mock())
                handler(websocket)
                self.websocket = websocket

            def new_page(self):
                self.page = FakePage()
                return self.page

        class FakeBrowser:
            def new_context(self, **kwargs):
                self.context = FakeContext()
                return self.context

            def close(self):
                self.closed = True

        class FakePlaywright:
            def __enter__(self):
                self.chromium = types.SimpleNamespace(launch=Mock(return_value=FakeBrowser()))
                return self

            def __exit__(self, *_args):
                return False

        context = types.SimpleNamespace(route_handler=None)
        fake_sync_api = types.ModuleType("playwright.sync_api")
        fake_sync_api.Error = type("PlaywrightError", (Exception,), {})
        fake_sync_api.sync_playwright = FakePlaywright
        fake_playwright = types.ModuleType("playwright")
        fake_playwright.sync_api = fake_sync_api
        with patch.dict(sys.modules, {"playwright": fake_playwright,
                                     "playwright.sync_api": fake_sync_api}), \
                patch("services.rendered_page_inspector._public_ipv4", return_value="93.184.216.34"):
            snapshot = inspect_rendered_public_page("https://example.com/login")

        self.assertEqual(snapshot.title, "Rendered Sign In")
        self.assertEqual([item.name for item in snapshot.elements], ["Email", "Continue"])
        self.assertTrue(requests[0].continued)
        self.assertEqual(requests[1].abort_reason, "blockedbyclient")
        self.assertEqual(requests[2].abort_reason, "blockedbyclient")


if __name__ == "__main__":
    unittest.main()