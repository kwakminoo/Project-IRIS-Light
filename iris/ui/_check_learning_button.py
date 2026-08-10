"""학습 버튼 스모크 — test_mode MainWindow + 상태 토글 (표시 확인용)."""

from __future__ import annotations

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

if QApplication.instance() is None:
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

# WebEngine import before app when possible
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
except Exception:
    pass

from iris.learning.models import LearningState
from iris.ui.window.main_window import MainWindow


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow(test_mode=True)
    win.show()
    assert hasattr(win._drag, "_btn_learning")
    assert win._drag._btn_learning is not None
    # 레이아웃: learning left of mic
    ctrl = None
    lay = win._drag.layout()
    assert lay is not None
    for i in range(lay.count()):
        item = lay.itemAt(i)
        if item is not None and item.layout() is not None:
            ctrl = item.layout()
    assert ctrl is not None
    widgets = [ctrl.itemAt(i).widget() for i in range(ctrl.count()) if ctrl.itemAt(i).widget()]
    assert widgets.index(win._drag._btn_learning) < widgets.index(win._drag._btn_mic)

    win._drag.set_learning_state(LearningState.IDLE)
    win._drag.set_learning_state(LearningState.RECORDING)
    win._drag.set_learning_state(LearningState.PROCESSING)
    win._drag.set_learning_state(LearningState.IDLE)
    win._set_mic_recording(True)
    win._set_mic_recording(False)

    # mock pipeline without real hooks
    from unittest import mock

    with mock.patch("iris.learning.manager.DemonstrationRecorder") as Rec:
        rec = Rec.return_value
        rec.start.return_value = None
        win._learning.start_recording()
        assert win._learning.state == LearningState.RECORDING
        win._learning.mark_processing()
        assert win._learning.state == LearningState.PROCESSING
        win._learning.mark_success({"name": "스모크 업무"})
        assert win._learning.state == LearningState.IDLE

    print("OK learning smoke: button left of mic, states, mic independent")
    win.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
