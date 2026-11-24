"""P4 — 사용자·에이전트 노출 핫패스에서 Hermes/헤르메스 브랜드 0.

실행: .venv\\Scripts\\python.exe -m iris.ui._check_hermes_user_branding_p4

INTERNAL_OK (검사 제외): hermes_* 모듈명, HERMES_* env, hermes-agent checkout,
LICENSE/NOTICE Nous MIT, 개발자 docstring·식별자.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 일상 UI·live activity·에러 안내·스킬 힌트에 남아 있으면 안 되는 문구.
HOT_PATH_FILES = (
    "iris/ui/window/main_window.py",
    "iris/ui/workers/iris_agent_workers.py",
    "iris/ui/chat/chat_panel.py",
    "iris/ui/chat/skill_mcp_dialogs.py",
    "iris/ui/settings/update_notify_box.py",
    "iris/ui/settings/settings_dialog.py",
    "iris/audio/text_normalizer.py",
    "iris/infrastructure/iris_agent_errors.py",
    "iris/infrastructure/iris_agent_client.py",
    "iris/system/iris_agent_gateway.py",
    "iris/system/iris_agent_tool_choice.py",
    "iris/system/iris_agent_memory_nudge.py",
    "iris/system/iris_agent_ollama_guard.py",
    "iris/ui/control_actions/action_catalog.json",
    "iris/ui/control_actions/agent_turn.py",
    "iris/ui/ai_hub/ai_hub_dialog.py",
    "integrations/hermes-skills/iris-control/iris-vibe-code/SKILL.md",
    "integrations/hermes-skills/iris-control/iris-mobile-mcp/SKILL.md",
)

BANNED = (
    "[Hermes tool]",
    "헤르메스",
    '"Hermes": "헤르메스"',
    "Hermes 업데이트가 가능",
    "헤르메스 업데이트 알림",
    "Hermes에 연결된 스킬",
    "Hermes gateway가 꺼져",
    "Hermes gateway를 시작",
    "Hermes gateway 기동 중",
    "Hermes 또는 Ollama가 켜져",
    "Hermes 게이트웨이 API 키",
    "restart Hermes gateway",
    "Hermes built-in",
    "Do not use Hermes `terminal`",
    "Hermes mobile-mcp",
    "Hermes model synced:",
    "Hermes model sync failed:",
    "Hermes 업데이트를 적용하는 중",
    'return "Hermes" if',
    "Hermes 웹검색",
    "Hermes에 연결되는",
    "· Hermes",
    "Hermes→Ollama",
    "Hermes가 '비슷한",
    "Hermes:",
    "Hermes HTTP",
    "Hermes 연결",
    "[Hermes]",
    "hermes agent.tool_choice",
    "Hermes-familiar",
    "separate Hermes builtin",
    "Hermes stream finished",
    "Hermes model API",
    "Hermes CLI",
    "Hermes api_key",
    "Hermes 채팅",
)


def main() -> None:
    from iris.infrastructure.iris_agent_errors import (
        explain_chat_error,
        scrub_upstream_hermes_cli_hints,
    )

    assert "[IRIS tool]" in (ROOT / "iris/ui/window/main_window.py").read_text(
        encoding="utf-8"
    )
    scrubbed = scrub_upstream_hermes_cli_hints(
        "custom rejected; run `hermes doctor` for details"
    )
    assert "hermes doctor" not in scrubbed.lower()
    assert "hermes doctor" not in explain_chat_error(
        "custom rejected; run hermes doctor"
    ).lower()

    hits: list[str] = []
    for rel in HOT_PATH_FILES:
        text = (ROOT / rel).read_text(encoding="utf-8")
        for banned in BANNED:
            if banned in text:
                hits.append(f"{rel}: {banned!r}")

    labels = (ROOT / "iris/system/setup_protocol.py").read_text(encoding="utf-8")
    for banned in (
        '"Hermes 설치"',
        '"Hermes gateway 기동"',
        '"Hermes API 키·서버 설정"',
    ):
        if banned in labels:
            hits.append(f"setup_protocol STEP: {banned!r}")

    chat_panel = (ROOT / "iris/ui/chat/chat_panel.py").read_text(encoding="utf-8")
    assert 'ChatNoticeAction("iris-agent-update://apply"' in chat_panel
    assert 'ChatNoticeAction("iris-hermes-update://apply"' not in chat_panel

    setup = (ROOT / "iris/system/setup_protocol.py").read_text(encoding="utf-8")
    assert "action_url=HERMES_INSTALL_URL" not in setup
    assert "hermes-agent.nousresearch.com/docs" not in setup
    assert 'HERMES_INSTALL_URL = "https://hermes-agent.nousresearch.com/install.ps1"' in setup
    logos = (ROOT / "iris/assets/setup_logos.py").read_text(encoding="utf-8")
    assert '"hermes": "H"' not in logos
    assert '"hermes": "IA"' in logos
    tts = (ROOT / "iris/audio/text_normalizer.py").read_text(encoding="utf-8")
    assert '"Hermes": "아이리스 에이전트"' in tts
    guard = (ROOT / "iris/system/iris_agent_ollama_guard.py").read_text(encoding="utf-8")
    assert "Iris Agent 채팅 경로 응답 있음" in guard
    assert "Hermes 채팅" not in guard

    assert not hits, "user/agent-facing Hermes copy:\n  " + "\n  ".join(hits)
    print("hermes_user_branding_p4 ok")


if __name__ == "__main__":
    main()
