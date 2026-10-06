"""Render real Qt widgets for chat typography, code, tables and streaming QA."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFontDatabase
from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.chat.chat_renderer import render_iris_message
from iris.ui.chat.chat_display import assistant_visible_text
from iris.ui.workspaces.workspace_iris_chat import WorkspaceIrisPanel

SAMPLES = [
    ("TCP 3-way handshake 과정을 초보자도 이해할 수 있게 설명해줘.",
     "## TCP 연결을 여는 세 번의 인사\n\nTCP는 데이터를 보내기 전에 서로 준비되었는지 확인합니다. 전화 통화를 시작할 때 인사를 주고받는 과정과 비슷합니다.\n\n"
     "### 1. SYN — 연결 요청\n\n클라이언트가 서버에게 **연결을 시작하고 싶어요**라고 요청합니다.\n\n"
     "### 2. SYN-ACK — 요청 확인\n\n서버가 요청을 받았다고 알리고, 자신도 준비되었다고 답합니다.\n\n"
     "### 3. ACK — 마지막 확인\n\n클라이언트가 서버의 응답을 확인합니다. 이제 양쪽이 데이터를 주고받을 수 있습니다.\n\n"
     "- 클라이언트 \\rightarrow 서버: SYN\n- 서버 \\rightarrow 클라이언트: SYN-ACK\n- 클라이언트 \\rightarrow 서버: ACK\n\n"
     "> 세 번의 메시지는 양쪽 모두 보낼 준비와 받을 준비가 되었는지 확인합니다."),
    ("Python으로 1부터 100까지 합을 구하는 코드를 작성하고 설명해줘.",
     "## Python 코드\n\n```python\ntotal = sum(range(1, 101))\nprint(total)  # 5050\n```\n\n"
     "- `range(1, 101)`은 1부터 100까지의 정수를 만듭니다.\n- `sum()`이 모든 수를 더합니다.\n\n결과는 **5050**입니다."),
    ("다음 내용을 표로 정리해줘.\n- SYN\n- SYN-ACK\n- ACK",
     "## 메시지 비교\n\n| 메시지 | 방향 | 역할 |\n|---|---|---|\n| SYN | 클라이언트 → 서버 | 연결 요청 |\n| SYN-ACK | 서버 → 클라이언트 | 요청 확인과 연결 준비 |\n| ACK | 클라이언트 → 서버 | 최종 확인 |"),
]

def main() -> None:
    app = QApplication.instance() or QApplication([])
    for font in ("malgun.ttf", "segoeui.ttf", "consola.ttf"):
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + font)
    out = Path(".iris_light_test_tmp/chat-readability")
    out.mkdir(parents=True, exist_ok=True)
    panel = ChatPanel()
    workspace = WorkspaceIrisPanel(name_prefix="QAWorkspace", placeholder="test")
    for width in (480, 1100):
        panel.resize(width, 850)
        workspace.resize(width, 850)
        panel.setStyleSheet("background-color:#0b1120;")
        workspace.setStyleSheet(workspace.styleSheet() + "QTextEdit {background-color:#0b1120;}")
        panel.show()
        workspace.show()
        app.processEvents()
        for index, (prompt, response) in enumerate(SAMPLES, 1):
            panel._log.clear()
            workspace._log.clear()
            panel.append_message_instant("You", prompt)
            panel.begin_stream_message("Iris", speech_sync=False)
            workspace.append_user(prompt)
            for offset in range(0, len(response), 7):
                panel.append_stream_chunk(response[offset:offset + 7])
                panel._flush_stream_ui()
                workspace.append_iris_chunk(response[offset:offset + 7])
                app.processEvents()
                assert panel._log.document().rootFrame().frameFormat().leftMargin() >= 12
                assert workspace._log.document().rootFrame().frameFormat().leftMargin() >= 12
            panel.end_stream_message(response)
            workspace.end_iris(response)
            app.processEvents()
            for label, widget in (("main", panel._log), ("workspace", workspace._log)):
                text = widget.toPlainText()
                assert "###" not in text and "**" not in text and "\\rightarrow" not in text, text
                assert widget.document().defaultFont().pixelSize() == 15
                if index == 2:
                    assert "5050" in text and "sum" in text
                widget.verticalScrollBar().setValue(0)
                widget.grab().save(str(out / f"{label}-{width}-{index}.png"))
            if index == 1:
                block = workspace._log.document().begin()
                paragraphs = []
                while block.isValid():
                    if "전화 통화" in block.text():
                        paragraphs.append(block)
                    block = block.next()
                assert paragraphs and paragraphs[0].blockFormat().bottomMargin() >= 14
                assert paragraphs[0].blockFormat().lineHeight() >= 160
        workspace.append_user('@"C:/example/report.txt"')
        assert "report.txt" in workspace._log.toPlainText()
        workspace.append_iris_chunk("짧은 답변입니다.")
        workspace.end_iris()
        workspace.append_iris_chunk("```python\nprint(1)\n")
        workspace.chat._flush_stream_ui()
        assert "print" in workspace._log.toPlainText() and "```" not in workspace._log.toPlainText()
        workspace.end_iris("```python\nprint(1)\n```")
    assert "\\rightarrow" in render_iris_message("```text\n\\rightarrow\n```")
    assert "sum" in assistant_visible_text(SAMPLES[1][1], streaming=False)
    panel.close()
    workspace.close()
    print("chat readability QA passed; screenshots:", out)

if __name__ == "__main__":
    main()
