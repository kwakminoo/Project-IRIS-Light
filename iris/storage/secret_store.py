"""로컬 시크릿 암호화 — Windows DPAPI, 그 외 기기 키 XOR."""

from __future__ import annotations

import base64
import hashlib
import os
import sys
from pathlib import Path

_DEVICE_KEY_PATH = Path.home() / ".iris-light" / ".device_key"


def _device_key() -> bytes:
    _DEVICE_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _DEVICE_KEY_PATH.is_file():
        _DEVICE_KEY_PATH.write_bytes(os.urandom(32))
    return _DEVICE_KEY_PATH.read_bytes()


def encrypt_secret(plain: str) -> str:
    if not plain:
        return ""
    data = plain.encode("utf-8")
    if sys.platform == "win32":
        try:
            import win32crypt  # type: ignore[import-untyped]

            blob = win32crypt.CryptProtectData(data, None, None, None, None, 0)
            return "dpapi:" + base64.b64encode(blob).decode("ascii")
        except ImportError:
            pass
    key = _device_key()
    enc = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return "local:" + base64.b64encode(enc).decode("ascii")


def decrypt_secret(token: str) -> str:
    if not token:
        return ""
    try:
        if token.startswith("dpapi:"):
            import win32crypt  # type: ignore[import-untyped]

            blob = base64.b64decode(token[6:])
            return win32crypt.CryptUnprotectData(blob, None, None, None, 0)[1].decode("utf-8")
        if token.startswith("local:"):
            key = _device_key()
            raw = base64.b64decode(token[6:])
            dec = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
            return dec.decode("utf-8")
    except Exception:
        return ""
    return ""


def secret_fingerprint(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()[:16]
