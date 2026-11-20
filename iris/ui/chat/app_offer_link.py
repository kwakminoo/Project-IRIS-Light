"""Chat log reopen links for ChatAppOffer (iris-app://)."""

from __future__ import annotations

from urllib.parse import quote, unquote

_SCHEME = "iris-app://"


def app_href(offer_id: str) -> str:
    return _SCHEME + quote(str(offer_id or ""), safe="")


def parse_app_href(anchor: str) -> str | None:
    raw = anchor or ""
    if not raw.startswith(_SCHEME):
        return None
    text = unquote(raw[len(_SCHEME) :]).strip()
    return text or None
