"""Chat app-form offers — domain types for interactive chat UI output.

Owns: ChatAppOffer kinds and materialization helpers.
Does not: SpeakTools, ChatPanel rendering, or control_actions wiring.
"""

from __future__ import annotations

import hashlib
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from iris.engine.app_ui import MAX_APP_UI_BYTES
from iris.engine.types import AppUiOfferEvent
from iris.ui.chat.app_host_bridge import AppHostOffer

KIND_PATH = "path"
KIND_EPHEMERAL = "ephemeral"
KIND_MCP_UI = "mcp_ui"
KIND_DIRECTORY = "directory"


@dataclass(frozen=True)
class ChatAppOffer:
    kind: str
    title: str
    offer_id: str = ""
    html_path: str = ""
    html: str = ""
    resource_uri: str = ""
    turn_id: str = ""


def new_offer_id() -> str:
    return uuid.uuid4().hex[:12]


def path_offer(
    title: str,
    html_path: str,
    *,
    resource_uri: str = "",
    turn_id: str = "",
    offer_id: str = "",
) -> ChatAppOffer:
    path = str(html_path or "").strip()
    if not path:
        raise ValueError("path_offer requires non-empty html_path")
    return ChatAppOffer(
        kind=KIND_PATH,
        title=(title or "").strip() or "앱",
        offer_id=offer_id or new_offer_id(),
        html_path=path,
        resource_uri=str(resource_uri or "").strip(),
        turn_id=str(turn_id or "").strip(),
    )


def ephemeral_offer(
    title: str,
    html: str,
    *,
    turn_id: str = "",
    offer_id: str = "",
    cache_dir: Path | None = None,
) -> ChatAppOffer:
    """Write HTML to a cache file and return an ephemeral offer.

    After a successful write, ``html`` on the returned offer is cleared to ``""``
    so large payloads are not kept in memory alongside ``html_path``.
    """
    text = html if isinstance(html, str) else ""
    if not text:
        raise ValueError("ephemeral_offer requires non-empty html")
    payload = text.encode("utf-8")
    if len(payload) > MAX_APP_UI_BYTES:
        raise ValueError(
            f"ephemeral_offer html exceeds MAX_APP_UI_BYTES ({MAX_APP_UI_BYTES})"
        )
    oid = offer_id or new_offer_id()
    root = cache_dir if cache_dir is not None else (
        Path(tempfile.gettempdir()) / "iris-app-ui" / "ephemeral"
    )
    digest = hashlib.sha256(payload).hexdigest()[:16]
    path = root / f"{digest}-{oid}.html"
    root.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return ChatAppOffer(
        kind=KIND_EPHEMERAL,
        title=(title or "").strip() or "앱",
        offer_id=oid,
        html_path=str(path),
        html="",
        turn_id=str(turn_id or "").strip(),
    )


def mcp_ui_offer(
    title: str,
    resource_uri: str,
    *,
    html_path: str = "",
    turn_id: str = "",
    offer_id: str = "",
) -> ChatAppOffer:
    uri = str(resource_uri or "").strip()
    if not uri:
        raise ValueError("mcp_ui_offer requires non-empty resource_uri")
    return ChatAppOffer(
        kind=KIND_MCP_UI,
        title=(title or "").strip() or "앱",
        offer_id=offer_id or new_offer_id(),
        html_path=str(html_path or "").strip(),
        resource_uri=uri,
        turn_id=str(turn_id or "").strip(),
    )


def directory_offer(
    title: str,
    resource_uri: str,
    *,
    html_path: str = "",
    turn_id: str = "",
    offer_id: str = "",
) -> ChatAppOffer:
    uri = str(resource_uri or "").strip()
    if not uri:
        raise ValueError("directory_offer requires non-empty resource_uri")
    return ChatAppOffer(
        kind=KIND_DIRECTORY,
        title=(title or "").strip() or "앱",
        offer_id=offer_id or new_offer_id(),
        html_path=str(html_path or "").strip(),
        resource_uri=uri,
        turn_id=str(turn_id or "").strip(),
    )


def to_app_host_offer(offer: ChatAppOffer) -> AppHostOffer:
    path = Path(str(offer.html_path or "").strip())
    if not offer.html_path or not path.is_file():
        raise ValueError("to_app_host_offer requires html_path pointing to an existing file")
    return AppHostOffer(
        title=(offer.title or "").strip() or "앱",
        html_path=str(path),
        offer_id=str(offer.offer_id or "").strip(),
    )


def to_app_ui_event(offer: ChatAppOffer) -> AppUiOfferEvent:
    # offer_id/kind stay on ChatAppOffer; AppUiOfferEvent keeps title/path/uri only.
    return AppUiOfferEvent(
        title=(offer.title or "").strip() or "앱",
        html_path=str(offer.html_path or "").strip(),
        resource_uri=str(offer.resource_uri or "").strip(),
    )
