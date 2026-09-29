import re
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

from models.api_testing import ApiContract, ApiEndpoint, ApiParameter, ApiResponseSpec


MAX_HTML_BYTES = 2 * 1024 * 1024
METHOD_PATTERN = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+([^\n<>'\"]+)", re.IGNORECASE)
STATUS_PATTERN = re.compile(r"\b([1-5][0-9]{2})\b")
HEADER_HINTS = {
    "authorization", "content-type", "accept", "request-id", "response-id",
    "correlation-id", "x-request-id", "partner-id", "api-key", "x-api-key",
}


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"h1", "h2", "h3", "h4", "p", "tr", "li", "pre", "code", "br", "div", "section"}:
            self.parts.append("\n")

    def handle_data(self, data):
        text = data.strip()
        if text:
            self.parts.append(text)

    def text(self) -> str:
        return re.sub(r"\n{3,}", "\n\n", "\n".join(self.parts))


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text()


def fetch_html(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Enter a valid http or https documentation URL.")
    with httpx.Client(timeout=httpx.Timeout(20.0, connect=5.0), follow_redirects=True) as client:
        response = client.get(url, headers={"User-Agent": "TestGen-AI/1.0"})
        response.raise_for_status()
        content = response.content[:MAX_HTML_BYTES + 1]
    if len(content) > MAX_HTML_BYTES:
        raise ValueError("HTML documentation is larger than the 2 MiB import limit.")
    return content.decode(response.encoding or "utf-8", errors="replace")


def _normalize_path(raw_path: str) -> str:
    path = raw_path.strip().rstrip(".,);")
    path = re.sub(r"^https?://[^/]+", "", path)
    path = re.sub(r"^\{[^}]+\}", "", path)
    if "?" in path:
        path = path.split("?", 1)[0]
    if not path.startswith("/"):
        path = "/" + path
    return path or "/"


def _query_params(raw_path: str) -> list[ApiParameter]:
    if "?" not in raw_path:
        return []
    query = raw_path.split("?", 1)[1]
    names = []
    for part in re.split(r"[&\s]+", query):
        name = part.split("=", 1)[0].strip("{} ")
        if name and re.match(r"^[A-Za-z_][A-Za-z0-9_-]*$", name):
            names.append(name)
    return [ApiParameter(name=name, location="query", required=False) for name in dict.fromkeys(names)]


def _path_params(path: str) -> list[ApiParameter]:
    return [ApiParameter(name=name, location="path", required=True)
            for name in re.findall(r"\{([^}/?]+)\}", path)]


def _headers(section: str) -> list[ApiParameter]:
    found: list[str] = []
    for candidate in re.findall(r"\b[A-Za-z][A-Za-z0-9-]{2,}\b", section):
        lower = candidate.lower()
        if lower in HEADER_HINTS or lower.startswith("x-") or lower.endswith("-id"):
            found.append(candidate)
    return [ApiParameter(name=name, location="header", required=True)
            for name in dict.fromkeys(found)]


def _body_fields(section: str) -> list[ApiParameter]:
    names: list[str] = []
    for name in re.findall(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*:', section):
        if name.lower() not in {"http", "status", "code", "message"}:
            names.append(name)
    return [ApiParameter(name=name, location="body", required=False)
            for name in dict.fromkeys(names[:20])]


def _responses(section: str) -> list[ApiResponseSpec]:
    statuses = [status for status in STATUS_PATTERN.findall(section)
                if status.startswith(("2", "3", "4", "5"))]
    return [ApiResponseSpec(status_code=status, description="Found in HTML documentation")
            for status in dict.fromkeys(statuses)]


def _section_around(text: str, start: int, next_start: int | None) -> str:
    left = start
    right = min(len(text), next_start if next_start is not None else start + 3000)
    return text[left:right]


def parse_html_api_doc(html_or_text: str, source_url: str = "") -> ApiContract:
    text = html_to_text(html_or_text) if "<" in html_or_text and ">" in html_or_text else html_or_text
    matches = list(METHOD_PATTERN.finditer(text))
    endpoints: list[ApiEndpoint] = []
    seen: set[tuple[str, str]] = set()
    for index, match in enumerate(matches):
        method = match.group(1).upper()
        raw_path = match.group(2)
        if "/" not in raw_path:
            continue
        if raw_path.lower().startswith(("http://", "https://")) and "/" not in raw_path[8:]:
            continue
        path = _normalize_path(raw_path)
        if path in {"/api", "/apis"}:
            continue
        key = (method, path)
        if key in seen:
            continue
        seen.add(key)
        next_start = matches[index + 1].start() if index + 1 < len(matches) else None
        section = _section_around(text, match.start(), next_start)
        heading = ""
        before = text[max(0, match.start() - 300):match.start()]
        heading_candidates = [line.strip() for line in before.splitlines() if 3 <= len(line.strip()) <= 90]
        if heading_candidates:
            heading = heading_candidates[-1]
        endpoints.append(ApiEndpoint(
            method=method,
            path=path,
            summary=heading,
            description=section[:1200],
            operation_id=f"{method.lower()}_{path.strip('/').replace('/', '_').replace('{', '').replace('}', '')}",
            headers=_headers(section),
            query_params=_query_params(raw_path),
            path_params=_path_params(path),
            body_fields=_body_fields(section),
            responses=_responses(section),
            source_reference=source_url or "Pasted documentation",
            warnings=["Extracted details need confirmation: headers, body fields and status codes may be ambiguous."],
        ))
    if not endpoints:
        raise ValueError("No API operations were found. Paste the API method/path section or use OpenAPI JSON.")
    title = "HTML API Documentation"
    title_match = re.search(r"\b([A-Z][A-Za-z0-9 ]{3,80} API(?: Guidelines| Reference| Documentation)?)\b", text)
    if title_match:
        title = title_match.group(1)
    base_url = ""
    return ApiContract(title=title, base_url=base_url, endpoints=endpoints, source_type="html")
