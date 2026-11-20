"""Agent confirm path: off-UI shell.run, unbounded UI confirm timeout, card gate prefer."""

from __future__ import annotations

from types import SimpleNamespace

from iris.system.control_surface import invoke_http_timeout, runs_off_ui_thread
from iris.ui.chat.shell_approval import ApprovalState
from iris.ui.control_bindings import _CARD_CONFIRM_ACTIONS, human_confirm_decision


class _FakeChat:
    def __init__(self) -> None:
        self.inserts: list[dict] = []

    def insert_tool_block(self, **kwargs) -> str:
        self.inserts.append(kwargs)
        return "card-1"


def main() -> int:
    assert runs_off_ui_thread("shell.run") is True
    assert runs_off_ui_thread("project.run") is True
    assert runs_off_ui_thread("email.send") is False

    assert invoke_http_timeout("ide.pick_open_file") is None
    assert invoke_http_timeout("ide.pick_open_folder") is None
    # confirm on UI thread must not use the 15s default
    assert invoke_http_timeout("email.send", confirm_required=True) is None
    assert invoke_http_timeout("email.add_account", confirm_required=True) is None
    # off-UI confirm waits via _call_on_ui_unbounded; HTTP timeout unused
    assert invoke_http_timeout("project.run", confirm_required=True) == 15.0
    assert invoke_http_timeout("shell.run", confirm_required=True) == 15.0
    assert invoke_http_timeout("settings.set", confirm_required=False) == 15.0

    hud_calls: list[str] = []

    def _hud() -> bool:
        hud_calls.append("hud")
        return True

    chat = _FakeChat()
    run_spec = SimpleNamespace(name="project.run", summary="run")
    approved = human_confirm_decision(
        run_spec,
        {"command": "git status"},
        chat=chat,
        ask_hud=_hud,
        on_ui=lambda fn: fn(),
        wait=lambda _bid: "run",
        load_approval=lambda: ApprovalState(),
    )
    assert approved is True
    assert hud_calls == []
    assert len(chat.inserts) == 1
    assert chat.inserts[0]["phase"] == "pending"
    assert chat.inserts[0]["command"] == "git status"

    skipped_chat = _FakeChat()
    denied = human_confirm_decision(
        run_spec,
        {"command": "rm -rf /"},
        chat=skipped_chat,
        ask_hud=_hud,
        on_ui=lambda fn: fn(),
        wait=lambda _bid: "skip",
        load_approval=lambda: ApprovalState(),
    )
    assert denied is False
    assert hud_calls == []

    auto_chat = _FakeChat()
    auto = human_confirm_decision(
        run_spec,
        {"command": "git status"},
        chat=auto_chat,
        ask_hud=_hud,
        on_ui=lambda fn: fn(),
        wait=lambda _bid: (_ for _ in ()).throw(AssertionError("waited")),
        load_approval=lambda: ApprovalState(mode_id="run_everything"),
    )
    assert auto is True
    assert hud_calls == []
    assert auto_chat.inserts == []

    email_spec = SimpleNamespace(name="email.send", summary="send")
    mail = human_confirm_decision(
        email_spec,
        {"to": "a@b.c"},
        chat=_FakeChat(),
        ask_hud=_hud,
        on_ui=lambda fn: fn(),
        wait=lambda _bid: (_ for _ in ()).throw(AssertionError("card for email")),
        load_approval=lambda: ApprovalState(),
    )
    assert mail is True
    assert hud_calls == ["hud"]

    no_chat = human_confirm_decision(
        run_spec,
        {"command": "git status"},
        chat=None,
        ask_hud=_hud,
        on_ui=lambda fn: fn(),
        wait=lambda _bid: (_ for _ in ()).throw(AssertionError("no insert")),
        load_approval=lambda: ApprovalState(),
    )
    assert no_chat is True
    assert hud_calls == ["hud", "hud"]

    assert "shell.run" in _CARD_CONFIRM_ACTIONS
    assert "project.write_file" in _CARD_CONFIRM_ACTIONS
    assert "email.send" not in _CARD_CONFIRM_ACTIONS

    print("agent confirm path ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
