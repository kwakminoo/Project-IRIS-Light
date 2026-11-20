"""Iris Agent 업데이트 채팅 프롬프트 자검. 실제 업데이트는 호출하지 않는다."""

from __future__ import annotations

from PyQt6.QtWidgets import QApplication

from iris.ui.chat.chat_panel import ChatPanel


def _main() -> None:
    app = QApplication([])
    panel = ChatPanel()
    panel.append_iris_agent_update_prompt(detail="abc1234 → def5678")
    blob = "\n".join(
        p.markdown
        for t in panel.transcript()._turns
        for p in t.parts
        if hasattr(p, "markdown")
    )
    assert "iris-agent-update://apply" in blob
    assert "iris-agent-update://later" in blob
    assert "[업데이트]" in blob and "[나중에]" in blob
    assert "Iris Agent 업데이트가 가능합니다" in blob
    assert panel._log.toPlainText().strip() == ""
    panel.dismiss_iris_agent_update_prompt("미룸")
    blob2 = "\n".join(
        p.markdown
        for t in panel.transcript()._turns
        for p in t.parts
        if hasattr(p, "markdown")
    )
    assert "iris-agent-update://apply" not in blob2
    assert "미룸" in blob2
    print("iris_agent_update prompt ok")


if __name__ == "__main__":
    _main()
