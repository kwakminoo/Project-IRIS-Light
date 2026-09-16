"""Startup core health probe — must not block Qt main thread."""

from __future__ import annotations

import threading

from PyQt6.QtCore import QThread, pyqtSignal

# ponytail: ensure Ollama/Hermes 기동 대기 포함 — 12s는 재부팅 직후에 부족함.
_HEALTH_PROBE_TIMEOUT_S = 90.0


class StartupHealthWorker(QThread):
    """Runs mark_core_ready_if_healthy off the UI thread."""

    finished_ok = pyqtSignal(bool)  # True = core ready, boot; False = show setup wizard

    def __init__(
        self,
        *,
        ollama_base_url: str,
        hermes_base_url: str,
        hermes_command: str,
        min_model: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._ollama_base_url = ollama_base_url
        self._hermes_base_url = hermes_base_url
        self._hermes_command = hermes_command
        self._min_model = min_model

    def _probe(self) -> bool:
        from iris.system.setup_protocol import (
            is_core_ready,
            is_setup_preview,
            mark_core_ready_if_healthy,
        )

        if is_setup_preview():
            return False
        # ponytail: 이미 core_ready면 Hermes stop/models warm을 기다리지 않는다.
        # warm은 인트로 시작 후 CoreWarmWorker가 담당. 안 그러면 '환경 확인 중'에
        # 고정되고 IDE 왕복(enter_from_void)으로만 UI가 살아나는 증상이 난다.
        if is_core_ready():
            return True
        return bool(
            mark_core_ready_if_healthy(
                ollama_base_url=self._ollama_base_url,
                hermes_base_url=self._hermes_base_url,
                hermes_command=self._hermes_command,
                min_model=self._min_model,
            )
        )

    def run(self) -> None:
        # ponytail: ThreadPoolExecutor+timeout은 Windows에서 shutdown이 프로브에
        # 묶일 수 있어 daemon thread + join(timeout)으로 끊는다.
        box: dict[str, bool] = {"ok": False, "done": False}

        def work() -> None:
            try:
                box["ok"] = bool(self._probe())
            except Exception:
                from iris.system.setup_protocol import is_core_ready

                box["ok"] = is_core_ready()
            finally:
                box["done"] = True

        t = threading.Thread(target=work, name="iris-startup-health", daemon=True)
        t.start()
        timeout_s = float(getattr(self, "_timeout_s", _HEALTH_PROBE_TIMEOUT_S))
        t.join(timeout=timeout_s)
        if box["done"]:
            ok = box["ok"]
        else:
            from iris.system.setup_protocol import is_core_ready

            ok = is_core_ready()
        self.finished_ok.emit(ok)


class CoreWarmWorker(QThread):
    """Boot 이후 Ollama/Hermes 기동 — UI 인트로를 막지 않는다."""

    def __init__(
        self,
        *,
        ollama_base_url: str,
        hermes_base_url: str,
        hermes_command: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._ollama_base_url = ollama_base_url
        self._hermes_base_url = hermes_base_url
        self._hermes_command = hermes_command

    def run(self) -> None:
        try:
            from iris.system.setup_protocol import _warm_core_services

            _warm_core_services(
                ollama_base_url=self._ollama_base_url,
                hermes_base_url=self._hermes_base_url,
                hermes_command=self._hermes_command,
            )
        except Exception:
            pass


if __name__ == "__main__":
    import time

    from PyQt6.QtCore import QCoreApplication

    app = QCoreApplication([])

    # --- timeout이 프로브 hang에 먹히지 않는지 ---
    class _HangWorker(StartupHealthWorker):
        def _probe(self) -> bool:  # noqa: ANN204
            time.sleep(3600)
            return False

    t0 = time.monotonic()
    w = _HangWorker(
        ollama_base_url="http://127.0.0.1:1/v1",
        hermes_base_url="http://127.0.0.1:2/v1",
        hermes_command="hermes",
    )
    w._timeout_s = 0.4
    got: list[bool] = []
    w.finished_ok.connect(got.append)
    w.start()
    while not got and time.monotonic() - t0 < 3.0:
        app.processEvents()
        time.sleep(0.05)
    assert got, "finished_ok never emitted on hang probe"
    assert time.monotonic() - t0 < 2.5, time.monotonic() - t0
    print("startup_health_worker ok")
