"""Bounded inspection of public, static HTML pages for web UI test design."""
import ipaddress
from html.parser import HTMLParser
import socket
from urllib.parse import urlparse

import httpx

from models.web_testing import WebPageElement, WebPageSnapshot


MAX_PAGE_BYTES = 1 * 1024 * 1024
MAX_ELEMENTS = 50
MAX_HEADINGS = 30
PAGE_TIMEOUT = httpx.Timeout(12.0, connect=4.0)
USER_AGENT = "TestGen-AI-Web-Inspector/1.0"


def _public_https_host(url: str) -> str:
    parsed = urlparse(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or
            parsed.password or parsed.port not in (None, 443)):
        raise ValueError("Use a public HTTPS page URL on port 443 without credentials.")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(
            not ipaddress.ip_address(item[4][0].split("%")[0]).is_global
            for item in addresses
        ):
            raise ValueError("Private or local web pages are not supported.")
    except (OSError, ValueError) as exc:
        if isinstance(exc, ValueError):
            raise
        raise ValueError("Could not resolve a public web page host.") from exc
    return parsed.hostname


class _PageSummaryParser(HTMLParser):
    """Extract a small accessible-name summary without scripts or page markup."""

    _TEXT_ROLES = {
        "button": "button",
        "a": "link",
        "textarea": "textbox",
        "select": "combobox",
    }
    _INPUT_ROLES = {
        "button": "button",
        "submit": "button",
        "reset": "button",
        "checkbox": "checkbox",
        "radio": "radio",
        "text": "textbox",
        "email": "textbox",
        "password": "textbox",
        "search": "searchbox",
        "url": "textbox",
        "tel": "textbox",
        "number": "spinbutton",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self.headings: list[str] = []
        self.elements: list[WebPageElement] = []
        self.labels: dict[str, str] = {}
        self._title_depth = 0
        self._description_depth = 0
        self._heading_depth = 0
        self._label_target = ""
        self._label_parts: list[str] = []
        self._label_controls: list[tuple[str, dict[str, str], str]] = []
        self._label_active = False
        self._capture: tuple[str, list[str], dict[str, str]] | None = None
        self._skip_depth = 0

    @staticmethod
    def _attrs(attrs):
        return {name.lower(): value or "" for name, value in attrs}

    def handle_starttag(self, tag, attrs):
        attributes = self._attrs(attrs)
        if tag in {"script", "style", "svg", "noscript"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._title_depth += 1
        if tag == "meta" and attributes.get("name", "").lower() == "description":
            self.description = attributes.get("content", "")[:300]
        if tag in {"h1", "h2", "h3", "h4"}:
            self._heading_depth += 1
            self._capture = ("heading", [], attributes)
        if tag == "label":
            self._label_active = True
            self._label_target = attributes.get("for", "")
            self._label_parts = []
            self._label_controls = []
        if tag == "input":
            input_type = attributes.get("type", "text").lower()
            role = self._INPUT_ROLES.get(input_type)
            if role and input_type != "hidden":
                if self._label_active:
                    self._label_controls.append((role, attributes, input_type))
                else:
                    self._record_control(role, attributes, input_type)
        elif tag in self._TEXT_ROLES and tag != "a":
            self._capture = ("control", [], {**attributes, "_role": self._TEXT_ROLES[tag]})
        elif tag == "a":
            self._capture = ("control", [], {**attributes, "_role": "link"})

    def handle_endtag(self, tag):
        if tag in {"script", "style", "svg", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag == "title" and self._title_depth:
            self._title_depth -= 1
        if tag == "label":
            label = " ".join(self._label_parts).strip()[:120]
            if self._label_target and label:
                self.labels[self._label_target] = label
            for role, attributes, input_type in self._label_controls:
                control_name = label or self.labels.get(attributes.get("id", ""), "")
                if control_name:
                    self._record_control(role, {**attributes, "aria-label": control_name}, input_type)
            self._label_target = ""
            self._label_parts = []
            self._label_controls = []
            self._label_active = False
        if self._capture and tag in {"h1", "h2", "h3", "h4", "button", "a", "textarea", "select"}:
            kind, parts, attributes = self._capture
            text = " ".join(" ".join(parts).split())[:120]
            if kind == "heading":
                if text and len(self.headings) < MAX_HEADINGS:
                    self.headings.append(text)
                self._heading_depth = max(0, self._heading_depth - 1)
            else:
                if self._label_active and self._label_parts and not attributes.get("aria-label"):
                    label = " ".join(self._label_parts).strip()[:120]
                    attributes = {**attributes, "aria-label": label}
                self._record_control(attributes.get("_role", ""), attributes, text=text)
            self._capture = None

    def handle_data(self, data):
        if self._skip_depth:
            return
        text = data.strip()
        if not text:
            return
        if self._title_depth:
            self.title = (self.title + " " + text).strip()[:160]
        if self._capture:
            self._capture[1].append(text)
        if self._label_active:
            self._label_parts.append(text)

    def _record_control(self, role, attributes, input_type="", text=""):
        if len(self.elements) >= MAX_ELEMENTS:
            return
        name = (attributes.get("aria-label") or
                self.labels.get(attributes.get("id", "")) or
                attributes.get("placeholder") or
                text or attributes.get("value") or attributes.get("title", ""))
        name = " ".join(name.split())[:120]
        if not role or not name:
            return
        strategy = "role"
        if attributes.get("placeholder") and role in {"textbox", "searchbox"}:
            strategy = "placeholder"
        self.elements.append(WebPageElement(role=role, name=name, locator_strategy=strategy))


def inspect_public_page(url: str) -> WebPageSnapshot:
    """Fetch one public HTTPS HTML document; redirects and private hosts are refused."""
    _public_https_host(url)
    try:
        with httpx.Client(timeout=PAGE_TIMEOUT, follow_redirects=False,
                          trust_env=False, verify=True) as client:
            with client.stream("GET", url, headers={"User-Agent": USER_AGENT}) as response:
                if response.is_redirect:
                    raise ValueError("Redirects are not followed. Enter the final HTTPS page URL.")
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if content_type and "text/html" not in content_type:
                    raise ValueError("The URL did not return an HTML page.")
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_PAGE_BYTES:
                        raise ValueError("The HTML page exceeds the 1 MiB inspection limit.")
                html = content.decode(response.encoding or "utf-8", errors="replace")
    except ValueError:
        raise
    except (httpx.HTTPError, OSError, UnicodeError) as exc:
        raise ValueError("Could not inspect that public HTTPS page.") from exc

    parser = _PageSummaryParser()
    parser.feed(html)
    return WebPageSnapshot(
        url=url,
        title=parser.title,
        description=parser.description,
        headings=parser.headings,
        elements=parser.elements,
    )