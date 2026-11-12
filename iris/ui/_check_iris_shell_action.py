"""TDD: shell.run is SpeakTools-visible and maps to an Iris Shell chat card."""

from __future__ import annotations

from iris.infrastructure.speak_capability import (
    PHASE4_ALLOWLIST,
    default_speak_tools,
    set_speak_surface,
)
from iris.system.iris_shell import parse_shell_job, run_shell_job
from iris.ui.chat.run_visibility import card_from_control_result
from iris.ui.control_actions.shell import _ide_companion_active


def main() -> None:
    set_speak_surface("home")
    assert PHASE4_ALLOWLIST.grant("shell.run") is not None
    names = default_speak_tools().engine_names()
    assert "shell.run" in names, names

    job = parse_shell_job({"command": "echo shell-action-ok"})
    out = run_shell_job(job)
    assert out.ok, out.summary
    envelope = {
        "ok": True,
        "action": "shell.run",
        "result": {
            "command": out.command,
            "cwd": out.cwd,
            "exit_code": out.exit_code,
            "stdout": out.stdout,
            "stderr": out.stderr,
            "summary": out.summary,
            "via": out.via,
        },
    }
    card = card_from_control_result("shell.run", envelope)
    assert card is not None
    assert card.title == "Iris Shell"
    assert "shell-action-ok" in (card.output + card.command)

    class _Win:
        _ui_mode = "companion"
        _companion_page = None
        _body_stack = None

    assert _ide_companion_active(_Win()) is True

    class _Home:
        _ui_mode = "normal"
        _companion_page = None
        _body_stack = None

    assert _ide_companion_active(_Home()) is False

    set_speak_surface("ide_companion")
    hidden = default_speak_tools().invoke("shell.run", {"command": "echo nope"})
    assert hidden.ok is False
    assert "not_allowed" in (hidden.error or ""), hidden
    set_speak_surface("home")
    print("iris_shell_action ok")


if __name__ == "__main__":
    main()
