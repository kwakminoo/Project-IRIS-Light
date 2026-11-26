"""앱 업데이트 프롬프트·상태 자검.

Update 안내는 ghost `_log`가 아니라 H1 transcript notice로 착지한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

ensure_qt_webengine_ready()

from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication(sys.argv)

from iris.core.message_parts import TextPart
from iris.system.app_update import UpdateStatus, check_for_update, read_local_sha
from iris.system.setup_protocol import local_inference_models, prefer_chat_model
from iris.ui.chat.chat_panel import ChatPanel


def _h1_blob(panel: ChatPanel) -> str:
    host = panel.transcript()
    chunks: list[str] = []
    for turn in host._turns:
        for part in turn.parts:
            if isinstance(part, TextPart):
                chunks.append(part.markdown)
    return "\n".join(chunks)


def _main() -> None:
    assert local_inference_models(["bge-m3:latest", "gemma4:e2b"]) == ["gemma4:e2b"]
    assert prefer_chat_model(["bge-m3", "gemma4:e2b"]) == "gemma4:e2b"

    panel = ChatPanel()
    panel.append_update_prompt(detail="abc1234 → def5678")
    blob = _h1_blob(panel)
    assert "iris-update://apply" in blob, blob
    assert "iris-update://later" in blob, blob
    assert "[Update]" in blob and "[Late]" in blob
    assert "업데이트가 가능합니다" in blob
    assert panel._log.toPlainText().strip() == "", "ghost _log must stay empty"
    panel.dismiss_update_prompt("미룸")
    blob2 = _h1_blob(panel)
    assert "iris-update://apply" not in blob2, blob2
    assert "미룸" in blob2

    st = UpdateStatus(available=True, local_sha="a" * 40, remote_sha="b" * 40, detail="x")
    assert st.available
    root = Path(__file__).resolve().parents[2]
    sha = read_local_sha(root)
    assert isinstance(sha, str)
    try:
        status = check_for_update(root=root)
        assert isinstance(status.available, bool)
    except Exception as exc:  # noqa: BLE001
        print("check_for_update skipped:", exc)

    print("app_update check ok")


if __name__ == "__main__":
    _main()
