"""TDD: chat.set_title Control action renames the active (or id) session."""

from __future__ import annotations

from unittest.mock import MagicMock

from iris.system.control_surface import ActionRegistry
from iris.ui.control_bindings import _register_actions


def _surface() -> tuple[MagicMock, ActionRegistry]:
    window = MagicMock()
    window._control_qt_invoker = None
    window._chat = None
    window._get_bound_ide_session.return_value = None
    window._conversation_id = 42
    window._chat_session.rename.return_value = None
    window._chat_session.title_of.return_value = "bench-phase4"
    surface = MagicMock()
    surface.registry = ActionRegistry()
    surface.booting = False
    _register_actions(window, surface)
    surface.registry.set_human_confirm(lambda spec, args: True)
    return window, surface.registry


def main() -> None:
    window, reg = _surface()
    names = {row["name"] for row in reg.catalog()}
    assert "chat.set_title" in names, "chat.set_title missing from Control catalog"

    missing = reg.invoke("chat.set_title", {})
    assert missing["ok"] is False
    assert "title" in str(missing.get("error") or "").lower()

    out = reg.invoke("chat.set_title", {"title": "bench-phase4"})
    assert out["ok"] is True, out
    window._chat_session.rename.assert_called_once_with(42, "bench-phase4")
    assert out["result"]["title"] == "bench-phase4"
    assert out["result"]["conversation_id"] == 42
    window._refresh_chat_history_panel.assert_called()

    window._chat_session.rename.reset_mock()
    other = reg.invoke("chat.set_title", {"id": 7, "title": "other"})
    assert other["ok"] is True, other
    window._chat_session.rename.assert_called_once_with(7, "other")

    window._chat_session.rename.return_value = "boom"
    failed = reg.invoke("chat.set_title", {"title": "x"})
    assert failed["ok"] is False
    assert "boom" in str(failed.get("error") or "")

    print("chat.set_title ok")


if __name__ == "__main__":
    main()
