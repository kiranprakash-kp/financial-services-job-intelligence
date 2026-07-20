"""Sanitization + debug-artifact helpers.

Reconnaissance and debug output must never contain cookies, tokens, session
identifiers, or personal data. These helpers centralize redaction so no report
or artifact leaks secrets.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

# Header names dropped entirely from any recorded metadata.
_SENSITIVE_HEADERS = {
    "cookie",
    "set-cookie",
    "authorization",
    "proxy-authorization",
    "x-csrf-token",
    "x-xsrf-token",
    "x-api-key",
    "apikey",
    "session",
    "x-session-id",
}

# Query params that commonly carry tracking / secret values.
_SENSITIVE_QUERY = {"token", "access_token", "sig", "signature", "sessionid", "_ga", "gclid"}


def sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    return {k: ("<redacted>" if k.lower() in _SENSITIVE_HEADERS else v) for k, v in headers.items()}


def sanitize_url(url: str) -> str:
    parts = urlparse(url)
    if not parts.query:
        return url
    q = parse_qs(parts.query, keep_blank_values=True)
    for key in list(q):
        if key.lower() in _SENSITIVE_QUERY:
            q[key] = ["<redacted>"]
    return urlunparse(parts._replace(query=urlencode(q, doseq=True)))


def sanitize_body(body: str | None, max_len: int = 2000) -> str | None:
    if body is None:
        return None
    text = body if len(body) <= max_len else body[:max_len] + "…<truncated>"
    for marker in ("password", "token", "secret", "authorization"):
        if marker in text.lower():
            return "<redacted: body contained a sensitive marker>"
    return text


def save_debug_artifact(debug_dir: Path, name: str, content: str, suffix: str = "txt") -> Path:
    debug_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    path = debug_dir / f"{stamp}_{name}.{suffix}"
    path.write_text(content, encoding="utf-8")
    return path


def dumps(obj: object) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, default=str)
