"""Agent confirm path: off-UI shell.run, unbounded UI confirm timeout, card gate prefer."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from iris.system.control_surface import invoke_http_timeout, runs_off_ui_thread
from iris.ui.chat.shell_approval import ApprovalState
from iris.ui import control_bindings
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
    attention: list[str] = []
    approved = human_confirm_decision(
        run_spec,
        {"command": "git status"},
        chat=chat,
        ask_hud=_hud,
        on_ui=lambda fn: fn(),
        wait=lambda _bid: "run",
        load_approval=lambda: ApprovalState(),
        on_attention=lambda: attention.append("attn"),
    )
    assert approved is True
    assert hud_calls == []
    assert len(chat.inserts) == 1
    assert chat.inserts[0]["phase"] == "pending"
    assert chat.inserts[0]["command"] == "git status"
    assert attention == ["attn"]

    skipped_chat = _FakeChat()
    denied = human_confirm_decision(
        run_spec,
        {"command": "rm -rf /"},
        chat=skipped_chat,
        ask_hud=_hud,
        on_ui=lambda fn: fn(),
        wait=lambda _bid: "skip",
        load_approval=lambda: ApprovalState(),
        on_attention=lambda: attention.append("attn"),
    )
    assert denied is False
    assert hud_calls == []
    assert attention == ["attn", "attn"]

    auto_chat = _FakeChat()
    attention.clear()
    auto = human_confirm_decision(
        run_spec,
        {"command": "git status"},
        chat=auto_chat,
        ask_hud=_hud,
        on_ui=lambda fn: fn(),
        wait=lambda _bid: (_ for _ in ()).throw(AssertionError("waited")),
        load_approval=lambda: ApprovalState(mode_id="run_everything"),
        on_attention=lambda: attention.append("attn"),
    )
    assert auto is True
    assert hud_calls == []
    assert auto_chat.inserts == []
    assert attention == []

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

    # U06: shell/project.run fail-closed — no chat card ⇒ deny, never HUD.
    deny_args: dict = {"command": "git status"}
    no_chat = human_confirm_decision(
        run_spec,
        deny_args,
        chat=None,
        ask_hud=_hud,
        on_ui=lambda fn: fn(),
        wait=lambda _bid: (_ for _ in ()).throw(AssertionError("no insert")),
        load_approval=lambda: ApprovalState(),
    )
    assert no_chat is False
    assert hud_calls == ["hud"]  # only email.send above
    assert deny_args.get("_iris_confirm_deny") == "approval_ui_unavailable"

    shell_spec = SimpleNamespace(name="shell.run", summary="shell")
    no_chat_shell = human_confirm_decision(
        shell_spec,
        {"command": "git status"},
        chat=None,
        ask_hud=_hud,
        on_ui=lambda fn: fn(),
        wait=lambda _bid: (_ for _ in ()).throw(AssertionError("no insert")),
        load_approval=lambda: ApprovalState(),
    )
    assert no_chat_shell is False
    assert hud_calls == ["hud"]

    # write_file may still HUD when card unavailable
    write_spec = SimpleNamespace(name="project.write_file", summary="write")
    write_ok = human_confirm_decision(
        write_spec,
        {"file": "a.py"},
        chat=None,
        ask_hud=_hud,
        on_ui=lambda fn: fn(),
        wait=lambda _bid: (_ for _ in ()).throw(AssertionError("no write card")),
        load_approval=lambda: ApprovalState(),
    )
    assert write_ok is True
    assert hud_calls == ["hud", "hud"]

    assert "shell.run" in _CARD_CONFIRM_ACTIONS
    assert "project.write_file" in _CARD_CONFIRM_ACTIONS
    assert "email.send" not in _CARD_CONFIRM_ACTIONS
    from iris.ui.control_bindings import _SHELL_NO_HUD_ACTIONS

    assert "shell.run" in _SHELL_NO_HUD_ACTIONS
    assert "project.run" in _SHELL_NO_HUD_ACTIONS

    bindings_src = Path(control_bindings.__file__).read_text(encoding="utf-8")
    assert "on_attention=" in bindings_src
    assert "_raise_attention(window)" in bindings_src
    assert "approval_ui_unavailable" in bindings_src

    from iris.system.control_surface import ActionSpec
    from iris.system.execution_policy import check_action_approval

    tagged: dict = {"command": "x"}
    policy = check_action_approval(
        ActionSpec(name="project.run", summary="r", risk="medium", confirm_required=True),
        tagged,
        lambda _s, a: human_confirm_decision(
            run_spec,
            a,
            chat=None,
            ask_hud=lambda: True,
            on_ui=lambda fn: fn(),
            wait=lambda _b: "run",
            load_approval=lambda: ApprovalState(),
        ),
    )
    assert policy.allowed is False
    assert policy.reason == "approval_ui_unavailable"

    print("agent confirm path ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
