"""Startup core health probe — must not block Qt main thread."""



from __future__ import annotations



from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout



from PyQt6.QtCore import QThread, pyqtSignal



# ponytail: Ollama/Hermes 동시 지연 시 UI는 살아 있어야 — 워커 전체 상한.

_HEALTH_PROBE_TIMEOUT_S = 12.0





class StartupHealthWorker(QThread):

    """Runs mark_core_ready_if_healthy off the UI thread."""



    finished_ok = pyqtSignal(bool)  # True = core ready, boot; False = show setup wizard



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



    def _probe(self) -> bool:

        from iris.system.setup_protocol import is_setup_preview, mark_core_ready_if_healthy



        if is_setup_preview():

            return False

        return bool(

            mark_core_ready_if_healthy(

                ollama_base_url=self._ollama_base_url,

                hermes_base_url=self._hermes_base_url,

                hermes_command=self._hermes_command,

            )

        )



    def run(self) -> None:

        try:

            with ThreadPoolExecutor(max_workers=1) as pool:

                fut = pool.submit(self._probe)

                ok = bool(fut.result(timeout=_HEALTH_PROBE_TIMEOUT_S))

        except FuturesTimeout:

            ok = False

        except Exception:

            ok = False

        self.finished_ok.emit(ok)

