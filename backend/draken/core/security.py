"""Minimal single-tenant auth: PBKDF2 password hashing + signed session cookies.

Draken is designed to run behind your own reverse proxy for an internal team, so
this deliberately stays dependency-free rather than pulling in a full auth stack.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from draken.core.config import settings

_ITERATIONS = 240_000
_ALGO = "pbkdf2_sha256"


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"{_ALGO}${_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iterations, salt_b64, digest_b64 = encoded.split("$")
    except ValueError:
        return False
    if algo != _ALGO:
        return False
    salt = base64.b64decode(salt_b64)
    expected = base64.b64decode(digest_b64)
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
    return hmac.compare_digest(candidate, expected)


def _sign(payload: bytes) -> str:
    sig = hmac.new(settings.secret_key.encode(), payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode().rstrip("=")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def issue_token(username: str) -> str:
    exp = int(time.time()) + settings.session_ttl_hours * 3600
    payload = json.dumps({"u": username, "exp": exp}, separators=(",", ":")).encode()
    return f"{_b64(payload)}.{_sign(payload)}"


def verify_token(token: str) -> str | None:
    """Return the username if the token is valid and unexpired."""
    try:
        body_b64, sig = token.split(".", 1)
        payload = _unb64(body_b64)
    except Exception:
        return None
    if not hmac.compare_digest(_sign(payload), sig):
        return None
    try:
        data = json.loads(payload)
    except Exception:
        return None
    if int(data.get("exp", 0)) < time.time():
        return None
    return data.get("u")
