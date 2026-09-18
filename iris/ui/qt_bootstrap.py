"""PyQt6 WebEngine startup contract — must run before QApplication.

IRIS IDE (Theia QWebEngineView) + email HTML viewer share one Chromium stack.
Importing WebEngine after QApplication without AA_ShareOpenGLContexts crashes Windows
(작업이 중단되었습니다 / exit 0xC0000409).

Creating QWebEngineView during MainWindow.__init__ blocks the UI thread for tens of
seconds (Windows shows 응답하지 않음). Defer view construction until first use.
"""

from __future__ import annotations

import os


DEFAULT_CHROMIUM_FLAGS = "--disable-gpu-compositing"


def _apply_chromium_flags() -> None:
    """설정이 있으면 그대로 두고, 없으면 기본값만 심는다.

    `--disable-gpu`는 GPU 프로세스를 막지 못하고 공유 컨텍스트 생성만 실패시킨다
    (실측: 기동마다 `ContextResult::kFatalFailure` 3건 + 컨텍스트 생성 실패 6건).
    합성만 끄면 오류 0건이고 첫 표시 시간도 동일했다(0.92s vs 0.99s).
    검은 화면이 남으면 `QTWEBENGINE_CHROMIUM_FLAGS`로 재빌드 없이 A/B 할 것.
    """
    if os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip():
        return
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = DEFAULT_CHROMIUM_FLAGS


def ensure_qt_webengine_ready() -> bool:
    """Set ShareOpenGLContexts before QApplication. Do not init Chromium here."""
    _apply_chromium_flags()
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    return True


def _self_check() -> None:
    import sys

    from PyQt6.QtWidgets import QApplication

    os.environ.pop("QTWEBENGINE_CHROMIUM_FLAGS", None)
    _apply_chromium_flags()
    flags = os.environ["QTWEBENGINE_CHROMIUM_FLAGS"]
    assert flags == DEFAULT_CHROMIUM_FLAGS, flags
    assert "--disable-gpu " not in f"{flags} ", f"GPU 전면 차단 재도입: {flags}"
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"
    _apply_chromium_flags()
    assert os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] == "--disable-gpu", "사용자 지정 플래그가 덮였음"
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = DEFAULT_CHROMIUM_FLAGS

    ensure_qt_webengine_ready()
    app = QApplication.instance() or QApplication(sys.argv)
    from iris.ui.window.main_window import MainWindow

    win = MainWindow(test_mode=True)
    assert win.windowTitle()
    print("qt_bootstrap ok")


if __name__ == "__main__":
    _self_check()
