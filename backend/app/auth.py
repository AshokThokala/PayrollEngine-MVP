"""Passwords and login tokens, using only the Python standard library.

Passwords: scrypt with a random 16-byte salt per user, stored as
    scrypt$<n>$<r>$<p>$<salt b64>$<hash b64>
Tokens: "<payload b64>.<HMAC-SHA256 b64>" where the payload is {"uid", "exp"}.
The signing key comes from SECRET_KEY; without it a random key is made at start-up,
so everyone has to log in again after a restart.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1
TOKEN_TTL_SECONDS = 12 * 60 * 60
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_SECRET = os.environ.get("SECRET_KEY") or secrets.token_urlsafe(48)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        check = hashlib.scrypt(password.encode(), salt=_unb64(salt), n=int(n), r=int(r), p=int(p))
        return hmac.compare_digest(check, _unb64(digest))
    except (ValueError, TypeError):
        return False


def password_problem(password: str) -> str | None:
    """Plain-English reason a password is too weak, or None."""
    if len(password) < 8:
        return "Use at least 8 characters"
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Use letters and at least one number"
    return None


def make_token(user_id: str, ttl: int = TOKEN_TTL_SECONDS, secret: str | None = None) -> str:
    payload = _b64(json.dumps({"uid": user_id, "exp": int(time.time()) + ttl}).encode())
    sig = hmac.new((secret or _SECRET).encode(), payload.encode(), hashlib.sha256).digest()
    return f"{payload}.{_b64(sig)}"


def read_token(token: str, secret: str | None = None) -> str | None:
    """Return the user id in a valid, unexpired token, else None."""
    try:
        payload, sig = token.split(".")
        expected = hmac.new((secret or _SECRET).encode(), payload.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(sig)):
            return None
        data = json.loads(_unb64(payload))
        if data["exp"] < time.time():
            return None
        return data["uid"]
    except (ValueError, KeyError, TypeError):
        return None
