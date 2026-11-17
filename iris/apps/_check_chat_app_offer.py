"""P0: ChatAppOffer domain types.

Run: .venv\\Scripts\\python.exe -m iris.apps._check_chat_app_offer
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from iris.apps.offer import (
    KIND_DIRECTORY,
    KIND_EPHEMERAL,
    KIND_MCP_UI,
    KIND_PATH,
    directory_offer,
    ephemeral_offer,
    mcp_ui_offer,
    path_offer,
    to_app_host_offer,
)
from iris.engine.app_ui import MAX_APP_UI_BYTES
from iris.ui.chat.app_host_bridge import AppHostOffer

_FIXTURE = (
    Path(__file__).resolve().parents[1] / "ui" / "chat" / "fixtures" / "app_host_ping.html"
)
_SNIPPET = "<html><body><h1>ephemeral-check</h1></body></html>"


def _assert_ephemeral_writes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        offer = ephemeral_offer("Ephemeral", _SNIPPET, cache_dir=Path(tmp), offer_id="chk1")
        assert offer.kind == KIND_EPHEMERAL
        assert offer.html == "", "html cleared after write"
        path = Path(offer.html_path)
        assert path.is_file(), offer.html_path
        text = path.read_text(encoding="utf-8")
        assert text.startswith("<html>"), text[:40]
        assert "ephemeral-check" in text


def _assert_oversized_rejected() -> None:
    huge = "x" * (MAX_APP_UI_BYTES + 1)
    try:
        ephemeral_offer("Too big", huge)
    except ValueError:
        return
    raise AssertionError("oversized html must raise ValueError")


def _assert_path_round_trip() -> None:
    assert _FIXTURE.is_file(), f"missing fixture: {_FIXTURE}"
    offer = path_offer("Ping", str(_FIXTURE), resource_uri="app_host_ping.html")
    host = to_app_host_offer(offer)
    assert isinstance(host, AppHostOffer)
    assert host.title == "Ping"
    assert host.offer_id == offer.offer_id
    assert Path(host.html_path).is_file()
    assert host.html_path == str(_FIXTURE) or Path(host.html_path).resolve() == _FIXTURE.resolve()


def _assert_kinds_distinct() -> None:
    kinds = {KIND_PATH, KIND_EPHEMERAL, KIND_MCP_UI, KIND_DIRECTORY}
    assert len(kinds) == 4, kinds
    path = path_offer("p", str(_FIXTURE))
    with tempfile.TemporaryDirectory() as tmp:
        eph = ephemeral_offer("e", _SNIPPET, cache_dir=Path(tmp))
    mcp = mcp_ui_offer("m", "ui://demo/card")
    direc = directory_offer("d", "app_host_ping.html")
    assert path.kind == KIND_PATH
    assert eph.kind == KIND_EPHEMERAL
    assert mcp.kind == KIND_MCP_UI
    assert direc.kind == KIND_DIRECTORY
    assert {path.kind, eph.kind, mcp.kind, direc.kind} == kinds


def main() -> None:
    _assert_ephemeral_writes()
    _assert_oversized_rejected()
    _assert_path_round_trip()
    _assert_kinds_distinct()
    print("ok: chat_app_offer")


if __name__ == "__main__":
    main()
