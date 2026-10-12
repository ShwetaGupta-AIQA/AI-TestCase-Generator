import unittest
from unittest.mock import patch

import httpx

from services.web_page_inspector import _PageSummaryParser, inspect_public_page


class WebPageInspectorTests(unittest.TestCase):
    def test_extracts_title_headings_and_accessible_controls(self):
        parser = _PageSummaryParser()
        parser.feed("""
            <html><head><title>Account Portal</title>
            <meta name="description" content="Manage your account"></head>
            <body><h1>Sign in</h1><label for="email">Email address</label>
            <input id="email" type="email"><input type="password" aria-label="Password">
            <button>Continue</button><a href="/help">Help center</a>
            <script><button>Ignore this control</button></script></body></html>
        """)
        self.assertEqual(parser.title, "Account Portal")
        self.assertEqual(parser.description, "Manage your account")
        self.assertEqual(parser.headings, ["Sign in"])
        controls = [(item.role, item.name, item.locator_strategy) for item in parser.elements]
        self.assertIn(("textbox", "Email address", "role"), controls)
        self.assertIn(("textbox", "Password", "role"), controls)
        self.assertIn(("button", "Continue", "role"), controls)
        self.assertIn(("link", "Help center", "role"), controls)
        self.assertNotIn("Ignore this control", [item.name for item in parser.elements])

    def test_uses_wrapping_label_text_for_form_control_names(self):
        parser = _PageSummaryParser()
        parser.feed("""
            <label>Customer name: <input name="custname"></label>
            <label>E-mail address: <input type="email" name="custemail"></label>
            <label><input type="radio" name="size" value="small"> Small</label>
            <label><input type="checkbox" name="topping" value="onion"> Onion</label>
            <label>Delivery instructions: <textarea name="comments"></textarea></label>
        """)
        controls = [(item.role, item.name) for item in parser.elements]
        self.assertIn(("textbox", "Customer name:"), controls)
        self.assertIn(("textbox", "E-mail address:"), controls)
        self.assertIn(("radio", "Small"), controls)
        self.assertIn(("checkbox", "Onion"), controls)
        self.assertIn(("textbox", "Delivery instructions:"), controls)

    def test_rejects_non_https_credentials_and_nonstandard_ports(self):
        for url in ["http://example.com", "https://user:pass@example.com",
                    "https://example.com:8443"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                inspect_public_page(url)

    @patch("services.web_page_inspector.socket.getaddrinfo")
    def test_rejects_private_dns_results(self, resolve):
        resolve.return_value = [(2, 1, 6, "", ("127.0.0.1", 443))]
        with self.assertRaisesRegex(ValueError, "Private or local"):
            inspect_public_page("https://example.com")

    @patch("services.web_page_inspector.socket.getaddrinfo")
    @patch("services.web_page_inspector.httpx.Client")
    def test_refuses_redirects(self, client_class, resolve):
        resolve.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
        response = httpx.Response(302, headers={"Location": "https://other.example/"})
        stream = client_class.return_value.__enter__.return_value.stream.return_value
        stream.__enter__.return_value = response
        with self.assertRaisesRegex(ValueError, "Redirects are not followed"):
            inspect_public_page("https://example.com")


if __name__ == "__main__":
    unittest.main()