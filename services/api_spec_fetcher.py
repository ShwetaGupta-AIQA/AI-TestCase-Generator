"""Bounded imports from public specification URLs."""
import ipaddress
import socket
from urllib.parse import urlparse

import httpx


def fetch_specification(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Use a public HTTPS specification URL without credentials.")
    if parsed.port not in (None, 443):
        raise ValueError("Specification URLs must use HTTPS port 443.")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise ValueError("Private or local specification URLs are unsupported. Upload the file instead.")
        with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
            with client.stream("GET", url) as response:
                if response.is_redirect:
                    raise ValueError("Use the final specification URL; redirects are unsupported.")
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > 2 * 1024 * 1024:
                        raise ValueError("Specification exceeds the 2 MiB import limit.")
                return content.decode("utf-8-sig")
    except (httpx.HTTPError, OSError, UnicodeError) as exc:
        raise ValueError("Could not read the public specification. Upload or paste its JSON/YAML instead.") from exc
