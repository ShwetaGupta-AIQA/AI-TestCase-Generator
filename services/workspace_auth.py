"""Small signed anonymous-workspace tokens for the free portfolio deployment.

Tokens are opaque to the client and contain no personal information.  They are
not a substitute for a full identity provider; Stage 2 uses them to isolate
saved runs without requiring a paid authentication service.
"""
import base64
import hashlib
import hmac
import os
from uuid import UUID, uuid4


def _secret():
    value = os.getenv("TESTGEN_WORKSPACE_SECRET", "")
    if len(value) < 32:
        raise RuntimeError("TESTGEN_WORKSPACE_SECRET must be at least 32 characters in Stage 2.")
    return value.encode("utf-8")


def issue_workspace():
    owner_id = str(uuid4())
    signature = hmac.new(_secret(), owner_id.encode("ascii"), hashlib.sha256).digest()
    token = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    return owner_id, f"{owner_id}.{token}"


def verify_workspace(token):
    try:
        owner_id, supplied = token.rsplit(".", 1)
        owner_id = str(UUID(owner_id))
        expected = hmac.new(_secret(), owner_id.encode("ascii"), hashlib.sha256).digest()
        padding = "=" * (-len(supplied) % 4)
        received = base64.urlsafe_b64decode(supplied + padding)
    except (AttributeError, ValueError, UnicodeError):
        return None
    return owner_id if hmac.compare_digest(expected, received) else None
