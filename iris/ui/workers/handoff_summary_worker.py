"""인수인계문 작성 워커 — 쓰던 모델에게 직접 요약을 시킨다.

모델을 갈아탈 때 가장 좋은 인수인계문은 **그때까지 대화를 끌고 온 모델**이 쓴
것이다. 무엇을 이미 해봤고 무엇이 막혔는지 판단이 들어가기 때문이다. 하지만
그러려면 HTTP 왕복이 필요해 UI 스레드에서 부르면 창이 멈춘다. 그래서 여기서 돈다.

창은 이 워커를 기다리지 않는다. 전환 즉시 규칙 기반 인수인계문을 먼저 걸어 두고,
요약이 제때 도착하면 그것으로 갈아끼운다(`MainWindow._on_handoff_summary_ready`).
늦게 오면 버린다 — 이미 나간 요청을 되돌릴 수는 없다.

세 백엔드를 모두 지원한다. 어느 쪽으로 부를지는 UI 스레드가 정해서 넘긴다.
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from iris.ui.workers.backend_call import (
    DEFAULT_TIMEOUT_SEC as BACKEND_TIMEOUT,
)
from iris.ui.workers.backend_call import BackendRoute, collect_reply

# 호출 자체는 backend_call 이 맡는다. 여기서는 "무엇을 물어보고 결과를 어디에
# 쓰는지"만 다룬다. SummaryRoute 는 BackendRoute 의 옛 이름 — 호출부 호환용.
SummaryRoute = BackendRoute

DEFAULT_TIMEOUT_SEC = BACKEND_TIMEOUT


class HandoffSummaryWorker(QThread):
    """구 모델에게 인수인계문을 쓰게 하고 텍스트만 돌려준다."""

    # (인수인계문, 이 요약이 붙을 아카이브 id)
    finished_ok = pyqtSignal(str, str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        route: SummaryRoute,
        messages: list[dict[str, str]],
        *,
        archive_id: str = "",
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._route = route
        self._messages = list(messages or [])
        self._archive_id = archive_id
        self._timeout_sec = float(timeout_sec)
        self._cancel = False

    def request_cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            text = self._collect()
        except Exception as exc:  # noqa: BLE001
            if not self._cancel:
                self.failed.emit(str(exc))
            return
        if self._cancel:
            return
        cleaned = (text or "").strip()
        if not cleaned:
            self.failed.emit("빈 인수인계문")
            return
        self.finished_ok.emit(cleaned, self._archive_id)

    def _collect(self) -> str:
        return collect_reply(
            self._route,
            self._messages,
            timeout_sec=self._timeout_sec,
            cancelled=lambda: self._cancel,
            # 사고 과정이 인수인계문에 섞이면 후임이 헷갈린다.
            think=False,
        )


if __name__ == "__main__":
    route = SummaryRoute(backend="ollama", model="m")
    assert route.base_url == "" and route.target is None and route.extra == {}
    assert SummaryRoute(backend="agent", model="m").backend == "agent"
    w = HandoffSummaryWorker(route, [{"role": "user", "content": "x"}], archive_id="a1")
    assert w._archive_id == "a1" and w._timeout_sec == DEFAULT_TIMEOUT_SEC
    w.request_cancel()
    assert w._cancel is True
    print("handoff_summary_worker self-check ok")
