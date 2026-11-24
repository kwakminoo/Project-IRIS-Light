"""Hermes 업데이트 채팅 프롬프트 자검. 실제 업데이트는 호출하지 않는다."""

from __future__ import annotations

from PyQt6.QtWidgets import QApplication

from iris.ui.chat.chat_panel import ChatPanel


def _transcript_markdown(panel: ChatPanel) -> str:
    return "\n".join(
        getattr(part, "markdown", "")
        for turn in panel.transcript()._turns
        for part in turn.parts
    )


def _main() -> None:
    app = QApplication([])
    panel = ChatPanel()
    panel.append_iris_agent_update_prompt(detail="abc1234 → def5678")
    markdown = _transcript_markdown(panel)
    assert "iris-agent-update://apply" in markdown
    assert "iris-agent-update://later" in markdown
    assert "iris-hermes-update://" not in markdown
    assert "[업데이트]" in markdown and "[나중에]" in markdown
    assert "Iris Agent 업데이트가 가능합니다" in markdown
    panel.dismiss_iris_agent_update_prompt("미룸")
    markdown2 = _transcript_markdown(panel)
    assert "iris-agent-update://apply" not in markdown2
    assert "미룸" in markdown2
    print("hermes_update prompt ok")


if __name__ == "__main__":
    _main()
