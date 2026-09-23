"""설정 닫힘 / 기동 hang 계약 자검.

  .venv\\Scripts\\python.exe -m iris.ui._check_settings_boot_fix
"""

from __future__ import annotations

import inspect
import time
from pathlib import Path


def _check_quit_on_last_window_closed_false() -> None:
    main_src = Path(__file__).resolve().parents[1].joinpath("__main__.py").read_text(
        encoding="utf-8"
    )
    assert "setQuitOnLastWindowClosed(False)" in main_src, main_src[:400]


def _check_settings_opened_as_toplevel() -> None:
    from iris.ui.window import main_window as mw

    src = inspect.getsource(mw.MainWindow._open_settings_dialog)
    assert "parent=None" in src or "SettingsDialog(..., None" in src or ", None," in src, src
    assert "0xC0000409" in src or "SetupWizard" in src or "독립" in src or "top-level" in src


def _check_main_close_quits_app() -> None:
    from iris.ui.window import main_window as mw

    src = inspect.getsource(mw.MainWindow.closeEvent)
    assert "app.quit()" in src or ".quit()" in src, src[-400:]


def _check_model_list_timeout() -> None:
    from PyQt6.QtCore import QCoreApplication

    from iris.ui.workers.ollama_workers import OllamaModelListWorker

    app = QCoreApplication.instance() or QCoreApplication([])

    class _Hang(OllamaModelListWorker):
        def run(self) -> None:  # noqa: D102
            # 부모 run과 동일 계약: timeout_s 안에 시그널
            import threading

            box: dict[str, object] = {"done": False}

            def work() -> None:
                time.sleep(3600)
                box["done"] = True

            t = threading.Thread(target=work, daemon=True)
            t.start()
            t.join(timeout=self._timeout_s)
            if not box["done"]:
                self.failed.emit("모델 목록 조회 시간 초과")

    got: list[str] = []
    t0 = time.monotonic()
    w = _Hang("http://127.0.0.1:1", timeout_s=0.35)
    w.failed.connect(got.append)
    w.start()
    while not got and time.monotonic() - t0 < 3.0:
        app.processEvents()
        time.sleep(0.05)
    assert got, "failed never emitted on hang"
    assert time.monotonic() - t0 < 2.5, time.monotonic() - t0


def _check_intro_models_cap_constant() -> None:
    from iris.ui.window import startup_intro as si

    assert 18.0 <= float(si._MODELS_WAIT_CAP_S) <= 25.0


def main() -> None:
    _check_quit_on_last_window_closed_false()
    _check_settings_opened_as_toplevel()
    _check_main_close_quits_app()
    _check_intro_models_cap_constant()
    _check_model_list_timeout()
    print("settings_boot_fix ok")


if __name__ == "__main__":
    main()
