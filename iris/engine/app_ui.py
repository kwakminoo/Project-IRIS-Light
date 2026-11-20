"""Resolve MCP tool _meta.ui into a local App Host offer.

Agent-readable:
- Owns: local resources and bounded MCP ``ui://`` HTML materialization.
- Does not: implement an MCP transport, talk to Qt, or load network URLs.
- Talks to: iris.engine.types.AppUiOfferEvent.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

if TYPE_CHECKING:
    from iris.engine.types import AppUiOfferEvent

_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "ui" / "chat" / "fixtures"
_KNOWN_FIXTURE_NAMES = frozenset({"app_host_ping.html"})
MAX_APP_UI_BYTES = 1_048_576
AppUiResourceResolver = Callable[[str], object]


def _resource_uri(meta: dict) -> str:
    ui = meta.get("ui")
    if isinstance(ui, dict):
        uri = ui.get("resourceUri")
        if uri is None:
            uri = ui.get("resource_uri")
        if uri is not None and str(uri).strip():
            return str(uri).strip()
    nested = meta.get("_meta")
    if isinstance(nested, dict):
        return _resource_uri(nested)
    return ""


def _file_url_path(uri: str) -> Path | None:
    parsed = urlparse(uri)
    if parsed.scheme.lower() != "file":
        return None
    raw = url2pathname(unquote(parsed.path))
    if not raw:
        return None
    return Path(raw)


def _fixture_path(uri: str) -> Path | None:
    name = Path(uri.replace("\\", "/")).name
    if name not in _KNOWN_FIXTURE_NAMES:
        return None
    path = _FIXTURE_DIR / name
    return path if path.is_file() else None


def _valid_ui_uri(uri: str) -> bool:
    parsed = urlparse(uri)
    if (
        not uri.lower().startswith("ui://")
        or parsed.scheme.lower() != "ui"
        or not parsed.netloc
    ):
        return False
    if (
        parsed.username
        or parsed.password
        or parsed.fragment
        or "\\" in uri
        or "\x00" in uri
    ):
        return False
    parts = [
        part
        for part in unquote(f"/{parsed.netloc}{parsed.path}").split("/")
        if part
    ]
    return ".." not in parts


def _html_bytes(uri: str, response: object) -> bytes | None:
    if not isinstance(response, dict):
        return None
    contents = response.get("contents")
    if not isinstance(contents, list):
        return None
    for content in contents:
        if not isinstance(content, dict):
            continue
        content_uri = str(content.get("uri") or "").strip()
        if content_uri and content_uri != uri:
            continue
        mime = (
            str(content.get("mimeType") or content.get("mime_type") or "")
            .split(";", 1)[0]
            .strip()
            .lower()
        )
        if mime != "text/html" and not mime.startswith("text/html+"):
            continue
        text = content.get("text")
        if isinstance(text, str):
            if len(text) > MAX_APP_UI_BYTES:
                continue
            payload = text.encode("utf-8")
        else:
            blob = content.get("blob")
            if (
                not isinstance(blob, str)
                or len(blob) > ((MAX_APP_UI_BYTES + 2) // 3) * 4
            ):
                continue
            try:
                payload = base64.b64decode(blob, validate=True)
                payload.decode("utf-8")
            except (ValueError, binascii.Error, UnicodeDecodeError):
                continue
        if len(payload) <= MAX_APP_UI_BYTES:
            return payload
    return None


def materialize_mcp_app_resource(
    uri: str,
    response: object,
    *,
    cache_dir: Path | None = None,
) -> Path | None:
    """Validate one MCP resources/read result and cache its HTML locally."""
    if not _valid_ui_uri(uri):
        return None
    payload = _html_bytes(uri, response)
    if payload is None:
        return None
    root = cache_dir or Path(tempfile.gettempdir()) / "iris-app-ui"
    digest = hashlib.sha256(uri.encode("utf-8") + b"\0" + payload).hexdigest()
    path = root / f"{digest}.html"
    try:
        root.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    except OSError:
        return None
    return path


def app_ui_from_tool_meta(
    meta: dict | None,
    *,
    default_title: str = "앱",
    resolver: AppUiResourceResolver | None = None,
    cache_dir: Path | None = None,
) -> AppUiOfferEvent | None:
    """Map tool UI metadata to a validated local App Host offer."""
    from iris.engine.types import AppUiOfferEvent

    if not isinstance(meta, dict):
        return None
    uri = _resource_uri(meta)
    if not uri:
        return None
    lowered = uri.lower()
    if lowered.startswith("http://") or lowered.startswith("https://"):
        return None

    title = (default_title or "앱").strip() or "앱"
    path: Path | None = None
    if lowered.startswith("ui:"):
        if not _valid_ui_uri(uri):
            return None
        # Host resolves ui:// later when sidecar has no MCP transport.
        if resolver is None:
            return AppUiOfferEvent(title=title, html_path="", resource_uri=uri)
        try:
            response = resolver(uri)
        except Exception:  # transport failures must not break the chat UI
            return None
        path = materialize_mcp_app_resource(uri, response, cache_dir=cache_dir)
    elif lowered.startswith("file:"):
        path = _file_url_path(uri)
    else:
        candidate = Path(uri)
        if candidate.is_absolute():
            path = candidate
        else:
            path = _fixture_path(uri)
    if path is None:
        return None
    return AppUiOfferEvent(title=title, html_path=str(path), resource_uri=uri)


def emit_app_ui_payload(
    meta_or_result: dict | None,
    *,
    default_title: str = "앱",
    resolver: AppUiResourceResolver | None = None,
    cache_dir: Path | None = None,
) -> dict | None:
    """Sidecar NDJSON fields for t=app_ui from tool meta or control/speak result."""
    if not isinstance(meta_or_result, dict):
        return None
    bags: list[dict] = [meta_or_result]
    for key in ("result", "data", "_meta"):
        nested = meta_or_result.get(key)
        if isinstance(nested, dict):
            bags.append(nested)
    for bag in bags:
        offer = app_ui_from_tool_meta(
            bag,
            default_title=default_title,
            resolver=resolver,
            cache_dir=cache_dir,
        )
        if offer is not None:
            return {
                "t": "app_ui",
                "title": offer.title,
                "html_path": offer.html_path,
                "resource_uri": offer.resource_uri,
            }
    return None
