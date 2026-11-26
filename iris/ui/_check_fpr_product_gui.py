"""Isolated GUI checks for the product MainWindow and its normal Control Surface."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def _until(predicate, *, timeout: float = 12) -> None:
    from PyQt6.QtTest import QTest

    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "GUI state did not arrive before timeout"
        QTest.qWait(50)


def _browser(win, root: Path) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QLineEdit, QPushButton

    wiki = next(btn for btn in win.findChildren(QPushButton) if btn.toolTip() == "Iris Wiki")
    browser = next(btn for btn in win.findChildren(QPushButton) if btn.toolTip() == "인터넷 브라우저")
    _until(lambda: wiki.isVisible() and wiki.visibleRegion().contains(wiki.rect().center()))
    QTest.mouseClick(wiki, Qt.MouseButton.LeftButton)
    assert win._obsidian_page.isVisible(), "Iris Wiki workspace was not mounted"
    assert browser.isVisible(), "Browser toolbar button is missing in Wiki"
    QTest.mouseClick(browser, Qt.MouseButton.LeftButton)
    url = win.findChild(QLineEdit, "IrisBrowserUrl")
    assert url is not None and url.isVisible(), "Browser address bar was not mounted"
    page = root / "browser-fixture.html"
    title = "IRIS FPR Browser Fixture"
    page.write_text(f"<!doctype html><title>{title}</title><h1>{title}</h1>", encoding="utf-8")
    url.setFocus()
    QTest.keySequence(url, "Ctrl+A")
    QTest.keyClicks(url, page.as_uri())
    QTest.keyClick(url, Qt.Key.Key_Return)
    panel = win._unified_shell.left_browser()
    assert panel is not None and panel.isVisible()
    _until(lambda: panel.view().title() == title)
    assert Path(panel.view().url().toLocalFile()).resolve() == page
    print("Iris Wiki click, Browser click and local WebEngine navigation passed")


def _process(win, root: Path) -> None:
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtTest import QTest

    from iris.system.request_approval import default_approval_ledger
    from iris.ui.chat.shell_approval import load

    _until(lambda: win._control_surface is not None and not win._control_surface.booting, timeout=16)
    surface = win._control_surface
    assert load().mode_id == "ask_every_time"

    def invoke(action: str, **args) -> dict:
        request = Request(
            f"http://127.0.0.1:{surface.bound_port}/v1/invoke",
            data=json.dumps({"action": "process.manage", "args": {"action": action, **args}}).encode(),
            headers={"Authorization": f"Bearer {surface.token}", "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=15) as response:
                return json.load(response)
        except HTTPError as exc:
            with exc:
                return json.load(exc)

    def click_pending(scheme: str, request) -> None:
        pending = False
        locations = []

        def located(point) -> None:
            nonlocal pending
            pending = False
            if point:
                locations.append(point)

        def press_link() -> bool:
            nonlocal pending
            if request.done():
                raise AssertionError(f"process responded before a GUI decision: {request.result()}")
            view = win._chat.transcript()._view
            if view is None or not view.isVisible():
                return False
            if locations:
                x, y = locations.pop()
                zoom = view.zoomFactor()
                target = view.focusProxy() or view
                pos = target.mapFrom(view, QPoint(round(x * zoom), round(y * zoom)))
                assert target.rect().contains(pos), "Shell Box approval link must be in the viewport"
                QTest.mouseClick(target, Qt.MouseButton.LeftButton, pos=pos)
                return True
            if pending:
                return False
            pending = True
            view.page().runJavaScript(
                """(() => { const link = [...document.querySelectorAll('a')].reverse()
                  .find(a => a.getAttribute('href')?.startsWith(%s) && a.getClientRects().length);
                  if (!link) return null;
                  link.scrollIntoView({block: 'center', behavior: 'instant'});
                  const box = link.getBoundingClientRect();
                  return [box.x + box.width / 2, box.y + box.height / 2]; })()""" % json.dumps(scheme),
                located,
            )
            return False

        _until(press_link, timeout=6)

    marker = "IRIS_FPR_PROCESS_STDOUT"
    fixture = root / "fixture.py"
    result_file = root / "process-ran.txt"
    fixture.write_text(
        "import os\nfrom pathlib import Path\n"
        "text = os.environ['IRIS_FPR_PROCESS_MARKER']\n"
        "Path('process-ran.txt').write_text(text, encoding='utf-8')\nprint(text)\n",
        encoding="utf-8",
    )
    start_args = {
        "argv": [sys.executable, str(fixture)],
        "cwd": str(root),
        "env": {"IRIS_FPR_PROCESS_MARKER": marker},
        "timeout_s": 10,
        "confirm": True,
    }
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(invoke, "start", **start_args)
        click_pending("iris-skip://", pending)
        _until(pending.done)
        denied = pending.result()
        assert not denied["ok"] and denied["error"] == "cancelled", denied
        assert not result_file.exists(), "model confirm:true bypassed the approval card"

        pending = pool.submit(invoke, "start", **start_args)
        click_pending("iris-run://", pending)
        _until(pending.done)
        accepted = pending.result()
        assert accepted["ok"], accepted
        record = accepted["result"]
        assert default_approval_ledger().get(record["request_id"]).used
        pending = pool.submit(invoke, "wait", run_id=record["run_id"], timeout_s=5)
        _until(pending.done)
        finished = pending.result()
        assert finished["ok"] and finished["result"]["exit_code"] == 0, finished
        pending = pool.submit(invoke, "read_output", run_id=record["run_id"])
        _until(pending.done)
        output = pending.result()
        assert output["ok"] and output["result"]["text"].strip() == marker, output
    assert result_file.read_text(encoding="utf-8") == marker
    print("Product Control process start: Skip refused, Run consumed approval, wait and stdout passed")


def _run(root: Path, check) -> None:
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication

    from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

    ensure_qt_webengine_ready()
    from iris.ui.window.main_window import MainWindow

    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(root))
    app = QApplication(["iris-product-gui-check"])
    assert app.platformName() not in {"offscreen", "minimal"}, "GUI smoke requires an interactive Qt platform"
    app.setQuitOnLastWindowClosed(False)

    # Already provisioned fixture for product paths with no inference dependency.
    from iris.system.setup_protocol import save_setup_state

    save_setup_state({"core_ready": True})
    with (
        patch.object(MainWindow, "_schedule_core_warm"),
        patch.object(MainWindow, "_repair_taskbar_pins"),
        patch.object(MainWindow, "_register_toast_click"),
    ):
        win = MainWindow()
        win.show()
        try:
            _until(lambda: win.windowOpacity() > 0.9 and win._intro is not None)
            check(win, root)
        finally:
            win.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=("browser", "process"))
    opts = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="iris-product-gui-", ignore_cleanup_errors=True) as work:
        root = Path(work).resolve()
        # Keep native user paths and any inherited provider credentials out of the fixture.
        isolated = {
            key: value for key, value in os.environ.items()
            if not key.startswith(("IRIS_", "HERMES_", "OLLAMA_"))
        }
        isolated.update(
            HOME=work,
            USERPROFILE=work,
            APPDATA=work,
            LOCALAPPDATA=work,
            PYTHON_DOTENV_DISABLED="1",
            IRIS_AGENT_ENABLED="0",
            IRIS_CONTROL_ENABLED="1" if opts.scenario == "process" else "0",
            IRIS_CONTROL_HOST="127.0.0.1",
            IRIS_CONTROL_PORT="0",
            IRIS_BROWSER_PROFILE=str(root / "browser"),
        )
        with patch.dict(os.environ, isolated, clear=True):
            _run(root, _process if opts.scenario == "process" else _browser)


if __name__ == "__main__":
    main()
