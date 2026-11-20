"""App Host open consent — JSON allowlist + pure gate.

Builtin apps never ask. Installed / external apps need one grant.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from iris.apps.directory import SOURCE_BUILTIN
from iris.system.iris_agent_control_sync import iris_state_dir

AskConsent = Callable[..., bool]


@dataclass(frozen=True)
class AppConsentDecision:
    app_id: str
    allowed: bool


def default_consent_path() -> Path:
    return iris_state_dir() / "apps" / "consent.json"


def _normalize_id(app_id: str) -> str:
    return (app_id or "").strip()


def load_allowlist(path: Path | None = None) -> tuple[str, ...]:
    target = default_consent_path() if path is None else path
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ()
    if not isinstance(raw, dict):
        return ()
    allow = raw.get("allowlist")
    if not isinstance(allow, list):
        return ()
    found: list[str] = []
    for item in allow:
        if isinstance(item, str) and item and item not in found:
            found.append(item)
    return tuple(found)


def _save_allowlist(ids: tuple[str, ...], path: Path | None = None) -> None:
    target = default_consent_path() if path is None else path
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps({"allowlist": list(ids)}, ensure_ascii=False, indent=2) + "\n"
    )
    try:
        if target.read_text(encoding="utf-8") == payload:
            return
    except OSError:
        pass
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(target)


def is_allowed(app_id: str, *, path: Path | None = None) -> bool:
    key = _normalize_id(app_id)
    if not key:
        return False
    return key in load_allowlist(path)


def grant(app_id: str, *, path: Path | None = None) -> None:
    key = _normalize_id(app_id)
    if not key:
        return
    current = load_allowlist(path)
    if key in current:
        return
    _save_allowlist((*current, key), path)


def deny(app_id: str, *, path: Path | None = None) -> None:
    key = _normalize_id(app_id)
    if not key:
        return
    current = load_allowlist(path)
    if key not in current:
        return
    _save_allowlist(tuple(item for item in current if item != key), path)


def decide_consent(
    app_id: str,
    *,
    source: str = "",
    path: Path | None = None,
    ask_consent: AskConsent | None = None,
    title: str = "",
    resource_uri: str = "",
    server_name: str = "",
) -> AppConsentDecision:
    """Return whether this app may open. Grants on a successful ask."""
    key = _normalize_id(app_id)
    if not key:
        return AppConsentDecision(app_id="", allowed=False)
    if (source or "").strip() == SOURCE_BUILTIN:
        return AppConsentDecision(app_id=key, allowed=True)
    if is_allowed(key, path=path):
        return AppConsentDecision(app_id=key, allowed=True)
    if ask_consent is None:
        return AppConsentDecision(app_id=key, allowed=False)
    try:
        ok = bool(
            ask_consent(
                app_id=key,
                title=title,
                resource_uri=resource_uri,
                server_name=server_name,
            )
        )
    except TypeError:
        ok = bool(ask_consent())
    if not ok:
        return AppConsentDecision(app_id=key, allowed=False)
    grant(key, path=path)
    return AppConsentDecision(app_id=key, allowed=True)
