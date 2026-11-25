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
    # FPR-01: auto still shows Shell Box (no Run/Skip wait).
    assert len(auto_chat.inserts) >= 1
    assert auto_chat.inserts[0]["phase"] == "pending"
    assert auto_chat.inserts[0]["command"] == "git status"
    assert attention == []

    shell_auto = _FakeChat()
    shell_spec_auto = SimpleNamespace(name="shell.run", summary="shell")
    shell_ok = human_confirm_decision(
        shell_spec_auto,
        {"command": "echo hi"},
        chat=shell_auto,
        ask_hud=_hud,
        on_ui=lambda fn: fn(),
        wait=lambda _bid: (_ for _ in ()).throw(AssertionError("waited")),
        load_approval=lambda: ApprovalState(mode_id="run_everything"),
        on_attention=lambda: attention.append("attn"),
    )
    assert shell_ok is True
    assert len(shell_auto.inserts) >= 1
    assert shell_auto.inserts[0].get("phase") == "pending"

    # FPR-07/08: email.send uses card — Run Everything must not auto-approve.
    email_spec = SimpleNamespace(name="email.send", summary="send", risk="high")
    mail_chat = _FakeChat()
    mail = human_confirm_decision(
        email_spec,
        {"to": "a@b.c", "subject": "hi", "body": "hello world"},
        chat=mail_chat,
        ask_hud=_hud,
        on_ui=lambda fn: fn(),
        wait=lambda _bid: "run",
        load_approval=lambda: ApprovalState(mode_id="run_everything"),
        on_attention=lambda: attention.append("attn"),
    )
    assert mail is True
    assert hud_calls == []
    assert len(mail_chat.inserts) == 1
    assert mail_chat.inserts[0]["phase"] == "pending"
    assert mail_chat.inserts[0]["title"].startswith("Email")
    assert "to=a@b.c" in mail_chat.inserts[0]["command"]
    assert "subject=hi" in mail_chat.inserts[0]["command"]
    assert "body=hello world" in mail_chat.inserts[0]["command"]
    assert mail_chat.inserts[0].get("allow_always") is False

    # email.add_account / remove_account → same card path, fail-closed, no HUD.
    add_spec = SimpleNamespace(name="email.add_account", summary="add", risk="high")
    add_chat = _FakeChat()
    add_ok = human_confirm_decision(
        add_spec,
        {"address": "a@b.c", "password": "secret", "label": "work"},
        chat=add_chat,
        ask_hud=_hud,
        on_ui=lambda fn: fn(),
        wait=lambda _bid: "run",
        load_approval=lambda: ApprovalState(mode_id="run_everything"),
    )
    assert add_ok is True
    assert hud_calls == []
    assert len(add_chat.inserts) == 1
    assert add_chat.inserts[0]["phase"] == "pending"
    assert "address=a@b.c" in add_chat.inserts[0]["command"]
    assert "label=work" in add_chat.inserts[0]["command"]
    assert "password" not in add_chat.inserts[0]["command"]
    assert add_chat.inserts[0].get("allow_always") is False

    rem_spec = SimpleNamespace(name="email.remove_account", summary="remove", risk="high")
    rem_chat = _FakeChat()
    rem_ok = human_confirm_decision(
        rem_spec,
        {"account_id": "acc-1"},
        chat=rem_chat,
        ask_hud=_hud,
        on_ui=lambda fn: fn(),
        wait=lambda _bid: "run",
        load_approval=lambda: ApprovalState(mode_id="run_everything"),
    )
    assert rem_ok is True
    assert hud_calls == []
    assert "account_id=acc-1" in rem_chat.inserts[0]["command"]
    assert rem_chat.inserts[0].get("allow_always") is False

    add_deny: dict = {"address": "a@b.c", "password": "x"}
    no_chat_add = human_confirm_decision(
        add_spec,
        add_deny,
        chat=None,
        ask_hud=_hud,
        on_ui=lambda fn: fn(),
        wait=lambda _bid: (_ for _ in ()).throw(AssertionError("no add card")),
        load_approval=lambda: ApprovalState(),
    )
    assert no_chat_add is False
    assert hud_calls == []
    assert add_deny.get("_iris_confirm_deny") == "approval_ui_unavailable"

    # Sensitive browser confirm → card, fail-closed (no HUD).
    browser_spec = SimpleNamespace(name="browser.click", summary="click", risk="medium")
    browser_chat = _FakeChat()
    browser_ok = human_confirm_decision(
        browser_spec,
        {"url": "https://pay.example/checkout", "name": "Buy now"},
        chat=browser_chat,
        ask_hud=_hud,
        on_ui=lambda fn: fn(),
        wait=lambda _bid: "run",
        load_approval=lambda: ApprovalState(mode_id="run_everything"),
    )
    assert browser_ok is True
    assert hud_calls == []
    assert "url=https://pay.example/checkout" in browser_chat.inserts[0]["command"]
    assert "click=Buy now" in browser_chat.inserts[0]["command"]

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
    assert hud_calls == []
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
    assert hud_calls == []

    # email.send fail-closed when card unavailable
    mail_deny: dict = {"to": "a@b.c"}
    no_chat_mail = human_confirm_decision(
        email_spec,
        mail_deny,
        chat=None,
        ask_hud=_hud,
        on_ui=lambda fn: fn(),
        wait=lambda _bid: (_ for _ in ()).throw(AssertionError("no mail card")),
        load_approval=lambda: ApprovalState(),
    )
    assert no_chat_mail is False
    assert hud_calls == []
    assert mail_deny.get("_iris_confirm_deny") == "approval_ui_unavailable"

    # browser sensitive fail-closed when card unavailable
    browser_deny: dict = {"url": "https://x"}
    no_chat_browser = human_confirm_decision(
        browser_spec,
        browser_deny,
        chat=None,
        ask_hud=_hud,
        on_ui=lambda fn: fn(),
        wait=lambda _bid: (_ for _ in ()).throw(AssertionError("no browser card")),
        load_approval=lambda: ApprovalState(),
    )
    assert no_chat_browser is False
    assert hud_calls == []
    assert browser_deny.get("_iris_confirm_deny") == "approval_ui_unavailable"

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
    assert hud_calls == ["hud"]

    assert "shell.run" in _CARD_CONFIRM_ACTIONS
    assert "project.write_file" in _CARD_CONFIRM_ACTIONS
    assert "email.send" in _CARD_CONFIRM_ACTIONS
    assert "email.add_account" in _CARD_CONFIRM_ACTIONS
    assert "email.remove_account" in _CARD_CONFIRM_ACTIONS
    from iris.ui.control_bindings import _SHELL_NO_HUD_ACTIONS

    assert "shell.run" in _SHELL_NO_HUD_ACTIONS
    assert "project.run" in _SHELL_NO_HUD_ACTIONS
    assert "email.send" in _SHELL_NO_HUD_ACTIONS
    assert "email.add_account" in _SHELL_NO_HUD_ACTIONS
    assert "email.remove_account" in _SHELL_NO_HUD_ACTIONS

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
