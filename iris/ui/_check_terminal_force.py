"""Companion 실행은 IDE 터미널(project.run)만. Hermes terminal / browser-만으로는 성공 아님."""

from __future__ import annotations

from pathlib import Path

from iris.runtime.turn_followthrough import counts_as_tool_ok
from iris.system.project_ops import is_static_web_file


def check_hermes_terminal_not_tool_ok() -> None:
    assert not counts_as_tool_ok("terminal ok")
    assert not counts_as_tool_ok("shell: python main.py ok")
    assert not counts_as_tool_ok("bash ok")
    assert counts_as_tool_ok("project.run ok")


def check_browser_preview_only_static() -> None:
    assert is_static_web_file("index.html")
    assert is_static_web_file("game/index.htm")
    assert not is_static_web_file("run_game.bat")
    assert not is_static_web_file("main.py")
    assert not is_static_web_file("app.js")  # not static html entry — run via terminal


def check_project_run_requires_reveal() -> None:
    src = Path(__file__).resolve().parent / "control_actions" / "project.py"
    text = src.read_text(encoding="utf-8")
    assert 'term.get("revealed") is False' in text or "revealed\") is False" in text
    assert "IDE integrated terminal panel was not revealed" in text
    assert 'via == "bridge_fallback"' in text or "bridge_fallback" in text


def check_hermes_disabled_config() -> None:
    from iris.system.hermes_iris_control_sync import verify_hermes_terminal_disabled

    ok, msg = verify_hermes_terminal_disabled()
    assert ok, msg


def main() -> None:
    check_hermes_terminal_not_tool_ok()
    check_browser_preview_only_static()
    check_project_run_requires_reveal()
    check_hermes_disabled_config()
    print("terminal_force check ok")


if __name__ == "__main__":
    main()
