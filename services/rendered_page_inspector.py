"""Opt-in JavaScript-rendered inspection with Chromium request containment."""
import ipaddress
from importlib import import_module
import os
import socket
from urllib.parse import urlparse

from models.web_testing import WebPageElement, WebPageSnapshot


NAVIGATION_TIMEOUT_MS = 15_000
RENDER_SETTLE_MS = 500
MAX_RENDERED_ELEMENTS = 50
MAX_RENDERED_HEADINGS = 30
MAX_PAGE_REQUESTS = 80
ALLOWED_RESOURCE_TYPES = {"document", "stylesheet", "script", "xhr", "fetch", "other"}


def rendered_inspection_enabled() -> bool:
    return os.getenv("TESTGEN_ENABLE_RENDERED_INSPECTION", "false").lower() == "true"


def _public_ipv4(hostname: str) -> str:
    try:
        results = socket.getaddrinfo(hostname, 443, family=socket.AF_INET, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("Could not resolve a public IPv4 address for rendered inspection.") from exc
    addresses = list(dict.fromkeys(result[4][0] for result in results))
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("Rendered inspection requires a hostname resolving only to public IPv4 addresses.")
    return addresses[0]


def _same_https_origin(url: str, hostname: str) -> bool:
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname is not None
        and parsed.hostname.encode("idna").decode("ascii").rstrip(".").lower()
        == hostname.encode("idna").decode("ascii").rstrip(".").lower()
        and port in (None, 443)
        and not parsed.username
        and not parsed.password
    )


def _render_request_allowed(url: str, hostname: str, resource_type: str, request_count: int) -> bool:
    return (
        request_count <= MAX_PAGE_REQUESTS
        and resource_type in ALLOWED_RESOURCE_TYPES
        and _same_https_origin(url, hostname)
    )


_EXTRACT_RENDERED_PAGE = """() => {
  const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim().slice(0, 120);
  const visible = (element) => {
    const style = getComputedStyle(element);
    return element.getClientRects().length > 0 && style.visibility !== 'hidden' && style.display !== 'none';
  };
  const nativeRoles = (element) => {
    const tag = element.tagName.toLowerCase();
    const type = (element.getAttribute('type') || 'text').toLowerCase();
    if (element.getAttribute('role')) return element.getAttribute('role').split(/\\s+/)[0];
    if (tag === 'button') return 'button';
    if (tag === 'a' && element.hasAttribute('href')) return 'link';
    if (tag === 'textarea') return 'textbox';
    if (tag === 'select') return element.multiple ? 'listbox' : 'combobox';
    if (tag !== 'input') return '';
    if (type === 'hidden') return '';
    if (type === 'checkbox' || type === 'radio') return type;
    if (type === 'button' || type === 'submit' || type === 'reset') return 'button';
    if (type === 'search') return 'searchbox';
    if (type === 'number') return 'spinbutton';
    return 'textbox';
  };
  const accessibleName = (element) => {
    const labelledBy = (element.getAttribute('aria-labelledby') || '').split(/\\s+/).filter(Boolean)
      .map((id) => document.getElementById(id)?.innerText || '').join(' ');
    const labels = element.labels ? Array.from(element.labels).map((label) => label.innerText || '').join(' ') : '';
    const name = element.getAttribute('aria-label') || labelledBy || labels ||
      element.getAttribute('placeholder') || element.innerText || element.getAttribute('alt') ||
      element.getAttribute('title') || '';
    return normalize(name);
  };
  const elements = [];
  for (const element of document.querySelectorAll('input,button,a,textarea,select,[role]')) {
    if (!visible(element)) continue;
    const role = nativeRoles(element);
    const name = accessibleName(element);
    if (!role || !name) continue;
    let locator_strategy = 'role';
    if (element.getAttribute('placeholder') && ['textbox', 'searchbox'].includes(role) &&
        !element.getAttribute('aria-label') && !(element.labels && element.labels.length)) {
      locator_strategy = 'placeholder';
    }
    elements.push({role, name, locator_strategy});
    if (elements.length >= 50) break;
  }
  const headings = Array.from(document.querySelectorAll('h1,h2,h3,h4'))
    .filter(visible).map((element) => normalize(element.innerText)).filter(Boolean).slice(0, 30);
  return {
    title: normalize(document.title).slice(0, 160),
    description: normalize(document.querySelector('meta[name="description"]')?.content).slice(0, 300),
    headings,
    elements
  };
}"""


def inspect_rendered_public_page(url: str) -> WebPageSnapshot:
    """Render one same-origin public HTTPS page; external requests are aborted."""
    parsed = urlparse(url)
    try:
        valid_port = parsed.port in (None, 443)
    except ValueError:
        valid_port = False
    hostname = parsed.hostname
    if (parsed.scheme != "https" or not hostname or parsed.username or parsed.password
            or not valid_port):
        raise ValueError("Use a public HTTPS page URL on port 443 without credentials.")
    hostname = hostname.encode("idna").decode("ascii").rstrip(".").lower()
    pinned_ipv4 = _public_ipv4(hostname)

    try:
        playwright_sync_api = import_module("playwright.sync_api")
        PlaywrightError = playwright_sync_api.Error
        sync_playwright = playwright_sync_api.sync_playwright
    except ImportError as exc:
        raise ValueError("Rendered inspection is unavailable: install the Playwright dependency and Chromium browser.") from exc

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-proxy-server",
                    "--disable-background-networking",
                    "--disable-webrtc",
                    f"--host-resolver-rules=MAP {hostname} {pinned_ipv4},EXCLUDE localhost",
                ],
            )
            try:
                context = browser.new_context(
                    service_workers="block",
                    accept_downloads=False,
                    ignore_https_errors=False,
                )

                request_count = 0

                def contain_request(route):
                    nonlocal request_count
                    request_count += 1
                    if _render_request_allowed(route.request.url, hostname,
                                               route.request.resource_type, request_count):
                        route.continue_()
                    else:
                        route.abort("blockedbyclient")

                context.route("**/*", contain_request)
                if hasattr(context, "route_web_socket"):
                    context.route_web_socket("**/*", lambda socket_route: socket_route.close())
                page = context.new_page()
                response = page.goto(url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
                if response is None or response.status >= 400:
                    status = response.status if response else "no response"
                    raise ValueError(f"Rendered page navigation failed ({status}).")
                if not _same_https_origin(page.url, hostname):
                    raise ValueError("Rendered inspection stopped because the page navigated outside its original HTTPS origin.")
                page.wait_for_timeout(RENDER_SETTLE_MS)
                summary = page.evaluate(_EXTRACT_RENDERED_PAGE)
                return WebPageSnapshot(
                    url=page.url,
                    title=summary.get("title", ""),
                    description=summary.get("description", ""),
                    headings=summary.get("headings", [])[:MAX_RENDERED_HEADINGS],
                    elements=[WebPageElement.model_validate(item)
                              for item in summary.get("elements", [])[:MAX_RENDERED_ELEMENTS]],
                )
            finally:
                browser.close()
    except ValueError:
        raise
    except PlaywrightError as exc:
        raise ValueError("Rendered page inspection failed or exceeded its navigation limit.") from exc