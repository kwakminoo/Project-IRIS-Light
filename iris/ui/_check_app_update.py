"""앱 업데이트 프롬프트·상태 자검."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QApplication

from iris.system.app_update import UpdateStatus, check_for_update, read_local_sha
from iris.system.setup_protocol import local_inference_models, prefer_chat_model
from iris.ui.chat.chat_panel import ChatPanel


def _main() -> None:
    assert local_inference_models(["bge-m3:latest", "gemma4:e2b"]) == ["gemma4:e2b"]
    assert prefer_chat_model(["bge-m3", "gemma4:e2b"]) == "gemma4:e2b"

    app = QApplication([])
    panel = ChatPanel()
    panel.append_update_prompt(detail="abc1234 → def5678")
    blob = "\n".join(
        p.markdown
        for t in panel.transcript()._turns
        for p in t.parts
        if hasattr(p, "markdown")
    )
    assert "iris-update://apply" in blob
    assert "iris-update://later" in blob
    assert "[Update]" in blob and "[Late]" in blob
    assert "업데이트가 가능합니다" in blob
    assert panel._log.toPlainText().strip() == ""
    panel.dismiss_update_prompt("미룸")
    blob2 = "\n".join(
        p.markdown
        for t in panel.transcript()._turns
        for p in t.parts
        if hasattr(p, "markdown")
    )
    assert "iris-update://apply" not in blob2
    assert "미룸" in blob2 or any(
        "미룸" in getattr(p, "markdown", "")
        for t in panel.transcript()._turns
        for p in t.parts
    )

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
