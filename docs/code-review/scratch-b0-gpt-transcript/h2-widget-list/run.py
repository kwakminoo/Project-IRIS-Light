"""H2 bakeoff throwaway: QScrollArea + per-part QWidget list for one assistant turn."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SAMPLE = HERE.parent / "shared" / "sample_turn.json"
sys.path.insert(0, str(REPO))

from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

ensure_qt_webengine_ready()

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView


def load_sample() -> dict:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def part_frame(title: str, child: QWidget) -> QFrame:
    box = QFrame()
    box.setFrameShape(QFrame.Shape.StyledPanel)
    lay = QVBoxLayout(box)
    head = QLabel(title)
    head.setStyleSheet("font-weight:600;color:#94a3b8;")
    lay.addWidget(head)
    lay.addWidget(child)
    return box


def build_text(part: dict) -> QWidget:
    lab = QLabel(part.get("markdown", ""))
    lab.setWordWrap(True)
    lab.setTextFormat(Qt.TextFormat.MarkdownText)
    return part_frame("text", lab)


def build_writing(part: dict) -> QWidget:
    edit = QPlainTextEdit()
    edit.setPlainText(part.get("body", ""))
    edit.setMinimumHeight(140)
    edit.setObjectName("writing_edit")
    title = part.get("title") or "writing"
    return part_frame(f"writing · {title}", edit)


def build_code(part: dict) -> QWidget:
    src = part.get("source", "")
    tabs = QTabWidget()
    tabs.setObjectName("code_tabs")
    code = QPlainTextEdit()
    code.setPlainText(src)
    code.setReadOnly(True)
    code.setObjectName("code_source")
    preview = QWebEngineView()
    preview.setObjectName("code_preview")
    preview.setHtml(src, QUrl("about:blank"))
    preview.setMinimumHeight(160)
    tabs.addTab(code, "Code")
    tabs.addTab(preview, "Preview")
    name = part.get("filename") or "code"
    return part_frame(f"code · {name}", tabs)


def build_app(part: dict) -> QWidget:
    view = QWebEngineView()
    view.setObjectName("app_calc")
    view.setHtml(part.get("html", ""), QUrl("about:blank"))
    view.setMinimumHeight(180)
    title = part.get("title") or "app"
    return part_frame(f"app · {title}", view)


BUILDERS = {
    "text": build_text,
    "writing": build_writing,
    "code": build_code,
    "app": build_app,
}


class TurnWindow(QMainWindow):
    def __init__(self, turn: dict) -> None:
        super().__init__()
        self.setWindowTitle(f"H2 widget-list · {turn.get('id', 'turn')}")
        self.resize(720, 900)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.addWidget(QLabel(f"role={turn.get('role')}  parts={len(turn.get('parts', []))}"))
        self.writing_edit: QPlainTextEdit | None = None
        self.code_tabs: QTabWidget | None = None
        self.app_view: QWebEngineView | None = None
        for part in turn.get("parts", []):
            kind = part.get("type", "")
            builder = BUILDERS.get(kind)
            if builder is None:
                lay.addWidget(QLabel(f"(skip unknown type={kind})"))
                continue
            w = builder(part)
            lay.addWidget(w)
            if kind == "writing":
                self.writing_edit = w.findChild(QPlainTextEdit, "writing_edit")
            elif kind == "code":
                self.code_tabs = w.findChild(QTabWidget, "code_tabs")
            elif kind == "app":
                self.app_view = w.findChild(QWebEngineView, "app_calc")
        lay.addStretch(1)
        scroll.setWidget(host)
        self.setCentralWidget(scroll)


def run_checks(win: TurnWindow, app: QApplication) -> int:
    """Non-interactive smoke for the 3 bakeoff interactions. Exit 0 = pass."""
    results: dict[str, bool] = {}
    notes: list[str] = []

    # 1) writing edit
    edit = win.writing_edit
    ok_write = False
    if edit is not None and edit.isEnabled() and not edit.isReadOnly():
        before = edit.toPlainText()
        edit.setPlainText(before + "\n# H2 edit ok")
        ok_write = "# H2 edit ok" in edit.toPlainText()
        notes.append(f"writing: editable={ok_write}")
    else:
        notes.append("writing: missing or read-only")
    results["writing"] = ok_write

    # 2) code / preview toggle
    tabs = win.code_tabs
    ok_tabs = False
    if tabs is not None and tabs.count() >= 2:
        tabs.setCurrentIndex(0)
        a = tabs.tabText(tabs.currentIndex())
        tabs.setCurrentIndex(1)
        b = tabs.tabText(tabs.currentIndex())
        ok_tabs = a == "Code" and b == "Preview"
        notes.append(f"code-preview: Code→Preview toggle ok={ok_tabs}")
    else:
        notes.append("code-preview: tabs missing")
    results["code_preview"] = ok_tabs

    # 3) calculator click via JS
    view = win.app_view
    calc_holder: dict[str, object] = {"done": False, "ok": False, "text": ""}

    def on_calc_text(text: object) -> None:
        calc_holder["text"] = text
        calc_holder["ok"] = str(text).strip() == "= 99"
        calc_holder["done"] = True

    def poke_calc() -> None:
        if view is None:
            calc_holder["done"] = True
            return
        js = (
            "document.getElementById('a').value='40';"
            "document.getElementById('b').value='59';"
            "document.getElementById('go').click();"
            "document.getElementById('out').textContent;"
        )
        view.page().runJavaScript(js, on_calc_text)

    def finish() -> None:
        results["calculator"] = bool(calc_holder.get("ok"))
        notes.append(f"calculator: out={calc_holder.get('text')!r} ok={calc_holder.get('ok')}")
        print("H2 CHECKS:")
        for line in notes:
            print(" ", line)
        failed = [k for k, v in results.items() if not v]
        print("PASS" if not failed else f"FAIL {failed}")
        app.quit()

    def wait_calc(n: int = 0) -> None:
        if calc_holder["done"] or n > 40:
            if not calc_holder["done"]:
                notes.append("calculator: timeout waiting for WebEngine JS")
                calc_holder["ok"] = False
            finish()
            return
        QTimer.singleShot(100, lambda: wait_calc(n + 1))

    # give WebEngine a moment to load setHtml
    QTimer.singleShot(800, poke_calc)
    QTimer.singleShot(900, wait_calc)
    return app.exec()


def main() -> int:
    check = "--check" in sys.argv
    turn = load_sample()
    app = QApplication(sys.argv)
    win = TurnWindow(turn)
    win.show()
    if check:
        return run_checks(win, app)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
