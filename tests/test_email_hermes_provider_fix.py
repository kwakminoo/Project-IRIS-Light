"""메일 MCP + Hermes provider 오염 복구 자검."""

from __future__ import annotations

from iris.infrastructure.email_client import (
    MailSummary,
    build_agent_context,
    filter_summaries_since,
)
from iris.infrastructure.hermes_client import (
    infer_hermes_provider,
    is_hermes_syncable_model,
    is_iris_api_runtime_model,
)
from iris.system.control_surface import runs_off_ui_thread


def test_iris_api_model_not_synced_to_hermes() -> None:
    mid = "api:41025a6367b9:nvidia/nemotron-3-ultra-550b-a55b"
    assert is_iris_api_runtime_model(mid)
    assert not is_hermes_syncable_model(mid)
    assert infer_hermes_provider(mid) == "auto"
    assert infer_hermes_provider("gemma4:26b") == "ollama"


def test_agent_context_includes_inbox() -> None:
    inbox = [
        MailSummary("1", "Hello", "a@b.com", "2026-08-26 09:00", "hi"),
        MailSummary("2", "Old", "c@d.com", "2026-08-25 09:00", "old"),
    ]
    ctx = build_agent_context("me@x.com", None, inbox=inbox)
    assert "email.list_messages" in ctx
    assert "Hello" in ctx
    assert len(filter_summaries_since(inbox, "2026-08-26")) == 1


def test_iris_email_skill_exists() -> None:
    from iris.system.hermes_iris_control_sync import SKILL_NAMES, repo_skills_iris_control_dir

    assert "iris-email" in SKILL_NAMES
    skill = repo_skills_iris_control_dir() / "iris-email" / "SKILL.md"
    assert skill.is_file()
    text = skill.read_text(encoding="utf-8")
    assert "email.list_messages" in text
    assert "refresh" in text


def test_email_imap_actions_run_off_ui() -> None:
    """IMAP sync on Qt main → Windows 응답 없음. list/read 는 오프-UI."""
    assert runs_off_ui_thread("email.list_messages")
    assert runs_off_ui_thread("email.read_message")
    assert not runs_off_ui_thread("email.open_compose")
    assert not runs_off_ui_thread("email.send")
    assert runs_off_ui_thread("emulator.launch")


if __name__ == "__main__":
    test_iris_api_model_not_synced_to_hermes()
    test_agent_context_includes_inbox()
    test_iris_email_skill_exists()
    test_email_imap_actions_run_off_ui()
    print("test_email_hermes_provider_fix ok")
