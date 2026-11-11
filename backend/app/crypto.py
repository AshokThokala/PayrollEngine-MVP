"""Encryption for sensitive employee fields (PAN, bank account number).

The key comes from FIELD_ENCRYPTION_KEY (a Fernet key) or, if that is not set, is derived from
SECRET_KEY. Keep the key stable: data encrypted with one key cannot be read with another.
"""
from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

from . import auth


def _fernet() -> Fernet:
    key = os.environ.get("FIELD_ENCRYPTION_KEY")
    if not key:
        secret = os.environ.get("SECRET_KEY") or auth._SECRET
        key = base64.urlsafe_b64encode(hashlib.sha256(f"field-encryption:{secret}".encode()).digest()).decode()
    return Fernet(key.encode())


def encrypt(value: str | None) -> str | None:
    return None if not value else _fernet().encrypt(value.encode()).decode()


def decrypt(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        raise ValueError("Cannot decrypt a stored field: FIELD_ENCRYPTION_KEY or SECRET_KEY changed") from None


def mask(value: str | None, keep: int = 4) -> str | None:
    if not value:
        return None
    return "•" * max(len(value) - keep, 0) + value[-keep:]
