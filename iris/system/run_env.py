"""Scrubbed environment for child processes (Execution Runtime / shell).

Allowlist-only copy from the product process env. Secrets matching denylist
patterns are never passed through — including keys in ``extra``.
Does not claim sandbox isolation.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping

# Exact allowlist keys (case-insensitive match against source keys).
_ALLOW_EXACT = frozenset(
    {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "HOME",
        "USERPROFILE",
        "USERNAME",
        "LANG",
        "TERM",
        "VIRTUAL_ENV",
        "PYTHONHOME",
        "IRIS_ENVIRONMENT_ID",
    }
)

# Prefix allowlist (uppercased key startswith).
_ALLOW_PREFIX = ("LC_", "CONDA_")

# Denylist: substring patterns on uppercased key (case-insensitive).
_DENY_SUBSTR = (
    "API_KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "CREDENTIAL",
)

# Email-auth style keys (exact or prefix), even without PASSWORD in the name.
_DENY_EMAIL_AUTH = frozenset(
    {
        "MAIL_USER",
        "MAIL_USERNAME",
        "MAIL_PASS",
        "EMAIL_USER",
        "EMAIL_USERNAME",
        "EMAIL_PASS",
        "SMTP_USER",
        "SMTP_USERNAME",
        "SMTP_PASS",
        "IMAP_USER",
        "IMAP_USERNAME",
        "IMAP_PASS",
        "POP3_USER",
        "POP3_USERNAME",
        "POP3_PASS",
    }
)
_DENY_EMAIL_PREFIX = ("MAIL_", "SMTP_", "IMAP_", "POP3_", "EMAIL_")

_DENY_RE = re.compile(
    "|".join(re.escape(p) for p in _DENY_SUBSTR),
    re.IGNORECASE,
)


def _is_denied(key: str) -> bool:
    upper = key.upper()
    if _DENY_RE.search(upper):
        return True
    if upper in _DENY_EMAIL_AUTH:
        return True
    # Auth-ish email keys without generic substrings (e.g. SMTP_HOST stays).
    if any(upper.startswith(p) for p in _DENY_EMAIL_PREFIX):
        if upper.endswith(("_USER", "_USERNAME", "_PASS", "_AUTH", "_LOGIN")):
            return True
    return False


def _is_allowed(key: str, allow_keys: frozenset[str]) -> bool:
    upper = key.upper()
    if upper in allow_keys or upper in _ALLOW_EXACT:
        return True
    return any(upper.startswith(p) for p in _ALLOW_PREFIX)


def build_child_env(
    base: Mapping[str, str] | None = None,
    extra: Mapping[str, str] | None = None,
    *,
    allow_keys: Iterable[str] | None = None,
) -> dict[str, str]:
    """Build a scrubbed env dict for subprocesses.

    - From ``base`` (default ``os.environ``): keep allowlisted keys only.
    - Strip denylist patterns (secrets / tokens / email auth).
    - Merge ``extra`` (also denylist-stripped); non-allowlisted extras are kept
      when not denied so callers can pass run-scoped knobs.
    """
    src: Mapping[str, str] = os.environ if base is None else base
    extra_allow = frozenset(str(k).upper() for k in (allow_keys or ()))
    out: dict[str, str] = {}
    for k, v in src.items():
        key = str(k)
        if _is_denied(key):
            continue
        if not _is_allowed(key, extra_allow):
            continue
        out[key] = str(v)
    if extra:
        for k, v in extra.items():
            key = str(k)
            if _is_denied(key):
                continue
            out[key] = str(v)
    return out
