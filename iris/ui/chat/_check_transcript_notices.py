"""H1 lands system notices (update / error / note / STT); ghost `_log` stays empty.

Run: .venv\\Scripts\\python.exe -m iris.ui.chat._check_transcript_notices
"""

from __future__ import annotations

import sys

from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

ensure_qt_webengine_ready()

from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication(sys.argv)

from iris.apps.offer import path_offer
from iris.core.message_parts import TextPart
from iris.ui.chat.chat_notices import ChatNotice, ChatNoticeAction, notice_markdown
from iris.ui.chat.chat_panel import ChatPanel


def _h1_blob(panel: ChatPanel) -> str:
    host = panel.transcript()
    chunks: list[str] = []
    for turn in host._turns:
        chunks.append(turn.role)
        chunks.append(turn.msg_id)
        for part in turn.parts:
            if isinstance(part, TextPart):
                chunks.append(part.markdown)
    return "\n".join(chunks)


def _log_clean(panel: ChatPanel) -> None:
    plain = panel._log.toPlainText().strip()
    assert plain == "", f"ghost _log must stay empty, got: {plain!r}"


def _check_domain() -> None:
    n = ChatNotice(
        kind="update",
        body="업데이트가 가능합니다.",
        actions=(
            ChatNoticeAction("iris-update://apply", "[Update]"),
            ChatNoticeAction("iris-update://later", "[Late]"),
        ),
    )
    md = notice_markdown(n)
    assert "업데이트가 가능합니다" in md
    assert "[Update](iris-update://apply)" in md or "iris-update://apply" in md
    assert "[Late](iris-update://later)" in md or "iris-update://later" in md


def _check_prompts(panel: ChatPanel) -> None:
    panel.append_update_prompt(detail="abc → def")
    blob = _h1_blob(panel)
    assert "업데이트가 가능합니다" in blob, blob
    assert "iris-update://apply" in blob, blob
    assert "iris-update://later" in blob, blob
    _log_clean(panel)

    panel.dismiss_update_prompt()
    blob2 = _h1_blob(panel)
    assert "iris-update://apply" not in blob2, blob2
    assert "iris-update://later" not in blob2, blob2
    assert "업데이트가 가능합니다" in blob2, blob2
    _log_clean(panel)

    panel.append_iris_agent_update_prompt(detail="h1 → h2")
    blob = _h1_blob(panel)
    assert "Iris Agent 업데이트가 가능합니다" in blob, blob
    assert "iris-agent-update://apply" in blob, blob
    panel.dismiss_iris_agent_update_prompt()
    assert "iris-agent-update://apply" not in _h1_blob(panel)
    _log_clean(panel)

    panel.append_ollama_cloud_login_prompt("클라우드 로그인 필요")
    blob = _h1_blob(panel)
    assert "클라우드 로그인 필요" in blob, blob
    assert "iris-ollama-login" in blob, blob
    _log_clean(panel)

    panel.append_error_message("요약 오류", "detail-secret")
    blob = _h1_blob(panel)
    assert "요약 오류" in blob, blob
    assert "iris-error://" in blob, blob
    assert panel._log._error_details, "error detail store required"
    _log_clean(panel)

    panel.append_note("참고한 이전 대화")
    blob = _h1_blob(panel)
    assert "참고한 이전 대화" in blob, blob
    # no [재생] on notice turns (notice- msg_id skips TTS)
    assert "[재생]" not in blob or "iris-tts://" not in blob
    _log_clean(panel)


def _check_app_note(panel: ChatPanel) -> None:
    from tempfile import TemporaryDirectory
    from pathlib import Path

    with TemporaryDirectory() as tmp:
        html = Path(tmp) / "a.html"
        html.write_text(
            "<!DOCTYPE html><html><body>ok</body></html>", encoding="utf-8"
        )
        offer = path_offer("Mini", str(html), offer_id="note01")
        panel.append_app_note(offer)
        blob = _h1_blob(panel)
        assert "Mini" in blob, blob
        assert "iris-app://" in blob, blob
        assert "다시 보기" in blob, blob
        _log_clean(panel)


def _check_stt(panel: ChatPanel) -> None:
    panel.transcript().clear()
    panel._stt_pending = False
    panel._stt_pending_msg_id = ""

    panel.begin_stt_pending()
    blob = _h1_blob(panel)
    assert "iris-stt://pending" in blob, blob
    assert panel.has_stt_pending()
    _log_clean(panel)

    assert panel.complete_stt_pending("말해본 문장") is True
    blob = _h1_blob(panel)
    assert "말해본 문장" in blob, blob
    assert "iris-stt://pending" not in blob, blob
    assert not panel.has_stt_pending()
    _log_clean(panel)

    panel.begin_stt_pending()
    assert panel.has_stt_pending()
    panel.cancel_stt_pending()
    blob = _h1_blob(panel)
    assert "iris-stt://pending" not in blob, blob
    assert not panel.has_stt_pending()
    _log_clean(panel)


def main() -> int:
    _ = QApplication.instance() or _APP
    _check_domain()
    panel = ChatPanel()
    _check_prompts(panel)
    _check_app_note(panel)
    _check_stt(panel)
    print("transcript_notices ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
