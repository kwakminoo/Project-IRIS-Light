"""고정 창 감시 — 창 찾기, 화면 모델 선택, 알림 발생."""

from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase, mock

from iris.automation.window_controller import WindowInfo
from iris.infrastructure import local_vision
from iris.monitoring import pinned_monitor
from iris.monitoring.models import DetectionResult, StatusCategory
from iris.monitoring.pin_store import PinnedTarget, PinStore
from iris.monitoring.pinned_monitor import PinnedMonitorService, locate_window


def _win(title: str, hwnd: int, minimized: bool = False) -> WindowInfo:
    return WindowInfo(title=title, left=0, top=0, width=800, height=600, hwnd=hwnd, minimized=minimized)


class LocateWindowTests(TestCase):
    def test_same_hwnd_wins_even_if_title_changed(self) -> None:
        pin = PinnedTarget(title="문서 A - Google Chrome", hwnd=42)
        wins = [_win("문서 B - Google Chrome", 42), _win("문서 A - Google Chrome", 7)]
        self.assertEqual(locate_window(pin, wins).hwnd, 42)

    def test_exact_title_when_hwnd_gone(self) -> None:
        pin = PinnedTarget(title="빌드 로그", hwnd=99)
        self.assertEqual(locate_window(pin, [_win("빌드 로그", 5)]).hwnd, 5)

    def test_last_seen_title(self) -> None:
        pin = PinnedTarget(title="원래 제목", hwnd=0, current_title="바뀐 제목")
        self.assertEqual(locate_window(pin, [_win("바뀐 제목", 3)]).hwnd, 3)

    def test_single_window_of_same_app(self) -> None:
        """IRIS 를 다시 켜 hwnd 가 없고 탭도 바뀐 경우 — 같은 앱 창이 하나면 그것."""
        pin = PinnedTarget(title="문서 A - Google Chrome")
        wins = [_win("메모장", 1), _win("뉴스 - Google Chrome", 2)]
        self.assertEqual(locate_window(pin, wins).hwnd, 2)

    def test_ambiguous_same_app_is_not_guessed(self) -> None:
        pin = PinnedTarget(title="문서 A - Google Chrome")
        wins = [_win("뉴스 - Google Chrome", 2), _win("메일 - Google Chrome", 3)]
        self.assertIsNone(locate_window(pin, wins))


class _FakeOllama:
    def __init__(self, names: list[str], caps: dict[str, list[str]] | None = None) -> None:
        self.base_url = "http://fake"
        self._names = names
        self._caps = caps or {}

    def list_models(self):
        return [SimpleNamespace(name=n, is_cloud=False) for n in self._names]

    def show_model(self, name: str, timeout_sec: float = 0):
        return {"capabilities": self._caps.get(name, [])}


class ResolveVisionModelTests(TestCase):
    def setUp(self) -> None:
        local_vision.forget_cache()

    def test_prefers_default_vision_model(self) -> None:
        client = _FakeOllama(["gemma4:e4b", "qwen2.5vl:3b"])
        model, why = local_vision.resolve_vision_model(client, "gemma4:e4b")
        self.assertEqual(model, "qwen2.5vl:3b")
        self.assertEqual(why, "")

    def test_chat_model_without_vision_capability_is_rejected(self) -> None:
        """이름은 비전처럼 보여도 Ollama가 vision 을 안 주면 쓰지 않는다 (gemma4 실제 사례)."""
        client = _FakeOllama(["gemma4:e4b"], {"gemma4:e4b": ["completion", "tools"]})
        model, why = local_vision.resolve_vision_model(client, "gemma4:e4b")
        self.assertIsNone(model)
        self.assertIn("설치", why)

    def test_chat_model_with_vision_capability_is_used(self) -> None:
        client = _FakeOllama(["llava:7b"], {"llava:7b": ["completion", "vision"]})
        model, _ = local_vision.resolve_vision_model(client, "llava:7b")
        self.assertEqual(model, "llava:7b")

    def test_ollama_down_is_reported_not_cached(self) -> None:
        client = _FakeOllama([])
        client.list_models = mock.Mock(side_effect=RuntimeError("연결 거부"))
        model, why = local_vision.resolve_vision_model(client, "")
        self.assertIsNone(model)
        self.assertIn("Ollama", why)
        client.list_models = lambda: [SimpleNamespace(name="qwen2.5vl:3b", is_cloud=False)]
        model, _ = local_vision.resolve_vision_model(client, "")
        self.assertEqual(model, "qwen2.5vl:3b")


class ServiceTests(TestCase):
    def _service(self, store: PinStore) -> PinnedMonitorService:
        settings = SimpleNamespace(ollama_base_url="http://fake/v1")
        return PinnedMonitorService(store, settings, lambda: "gemma4:e4b")  # type: ignore[arg-type]

    def _run(self, svc, windows, model=("qwen2.5vl:3b", ""), result=None):
        result = result or DetectionResult(
            StatusCategory.ERROR_DETECTED, 0.9, "빨간 에러", "로그 확인", summary="터미널"
        )
        with mock.patch(
            "iris.automation.window_controller.list_visible_windows", return_value=windows
        ), mock.patch(
            "iris.infrastructure.local_vision.resolve_vision_model", return_value=model
        ), mock.patch.object(
            pinned_monitor, "capture_window_by_hwnd", return_value=object()
        ), mock.patch.object(
            pinned_monitor, "capture_result_to_png_bytes", return_value=b"png"
        ), mock.patch.object(
            pinned_monitor, "detect_window_state", return_value=result
        ) as detect:
            svc._analyze_all("gemma4:e4b")
        return detect

    def test_alert_when_title_changed_but_same_window(self) -> None:
        store = PinStore()
        store.pin("문서 A - Google Chrome", 42)
        svc = self._service(store)
        reports: list[tuple] = []
        svc.report.connect(lambda *a: reports.append(a))

        detect = self._run(svc, [_win("문서 B - Google Chrome", 42)])

        self.assertEqual(detect.call_args.args[1], "qwen2.5vl:3b")
        pin = store.get("문서 A - Google Chrome")
        self.assertEqual(pin.status, StatusCategory.ERROR_DETECTED)
        self.assertEqual(pin.summary, "터미널")
        self.assertEqual(pin.current_title, "문서 B - Google Chrome")
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0][1], "ERROR_DETECTED")

    def test_same_state_twice_alerts_once(self) -> None:
        store = PinStore()
        store.pin("빌드", 5)
        svc = self._service(store)
        reports: list[tuple] = []
        svc.report.connect(lambda *a: reports.append(a))
        self._run(svc, [_win("빌드", 5)])
        self._run(svc, [_win("빌드", 5)])
        self.assertEqual(len(reports), 1)

    def test_no_vision_model_explains_and_asks_once(self) -> None:
        store = PinStore()
        store.pin("빌드", 5)
        svc = self._service(store)
        asked: list[str] = []
        svc.vision_missing.connect(asked.append)
        why = "화면을 볼 수 있는 모델이 없어요 — qwen2.5vl:3b 설치가 필요해요."
        detect = self._run(svc, [_win("빌드", 5)], model=(None, why))
        self._run(svc, [_win("빌드", 5)], model=(None, why))

        detect.assert_not_called()
        self.assertEqual(store.get("빌드").reason, why)
        self.assertEqual(len(asked), 1)

    def test_status_lines_for_chat(self) -> None:
        store = PinStore()
        store.pin("빌드", 5)
        svc = self._service(store)
        self.assertEqual(svc.status_lines(), ["- 빌드: 아직 분석 전"])
        self._run(svc, [_win("빌드", 5)])
        line = svc.status_lines()[0]
        self.assertIn("에러 발생", line)
        self.assertIn("화면: 터미널", line)


class ChangeWatchTests(TestCase):
    def _cap(self, value: int = 200, box: tuple[int, int, int, int] | None = None, fill: int = 0):
        from iris.monitoring.screen_capture import CaptureResult

        w, h = 800, 600
        rows = [bytearray([value] * (w * 3)) for _ in range(h)]
        if box:
            x0, y0, x1, y1 = box
            for y in range(y0, y1):
                rows[y][x0 * 3 : x1 * 3] = bytes([fill] * ((x1 - x0) * 3))
        return CaptureResult(w, h, bytes(b"".join(rows)))

    def test_caret_blink_is_not_a_change_but_new_text_is(self) -> None:
        sig = pinned_monitor.screen_signature
        base = sig(self._cap())
        self.assertFalse(pinned_monitor.screen_changed(base, sig(self._cap(box=(400, 300, 402, 316)))))
        self.assertTrue(pinned_monitor.screen_changed(base, sig(self._cap(box=(100, 400, 500, 440)))))
        self.assertTrue(pinned_monitor.screen_changed(None, base))

    def test_only_changed_window_is_analyzed(self) -> None:
        store = PinStore()
        store.pin("빌드", 5)
        store.pin("채팅", 6)
        store.set_hwnd("빌드", 5, "빌드")
        store.set_hwnd("채팅", 6, "채팅")
        settings = SimpleNamespace(ollama_base_url="http://fake/v1")
        svc = PinnedMonitorService(store, settings, lambda: "")  # type: ignore[arg-type]
        same, before = self._cap(), self._cap()
        svc._sigs = {"빌드": pinned_monitor.screen_signature(before), "채팅": pinned_monitor.screen_signature(before)}
        caps = {5: same, 6: self._cap(box=(0, 0, 800, 100))}
        emitted: list[list] = []
        svc._changed.disconnect()
        svc._changed.connect(emitted.append)
        with mock.patch.object(pinned_monitor, "capture_window_by_hwnd", side_effect=lambda h, **_: caps[h]), \
                mock.patch("ctypes.windll.user32.IsIconic", return_value=0):
            svc._watch(store.list_pins())
        self.assertEqual(emitted, [["채팅"]])

        # 방금 분석한 창은 3초 안에 다시 부르지 않는다
        svc._analyzed_at["채팅"] = pinned_monitor.time.monotonic()
        emitted.clear()
        with mock.patch.object(pinned_monitor, "capture_window_by_hwnd", side_effect=lambda h, **_: caps[h]), \
                mock.patch("ctypes.windll.user32.IsIconic", return_value=0):
            svc._watch(store.list_pins())
        self.assertEqual(emitted, [])


class StartupAndClosedPinTests(TestCase):
    def test_start_analyzes_saved_pins_right_away(self) -> None:
        store = PinStore()
        store.pin("빌드", 5)
        settings = SimpleNamespace(ollama_base_url="http://fake/v1")
        svc = PinnedMonitorService(store, settings, lambda: "")  # type: ignore[arg-type]
        with mock.patch.object(svc, "analyze_soon") as soon:
            svc.start()
        svc.stop()
        soon.assert_called_once()

    def test_start_without_pins_does_nothing(self) -> None:
        settings = SimpleNamespace(ollama_base_url="http://fake/v1")
        svc = PinnedMonitorService(PinStore(), settings, lambda: "")  # type: ignore[arg-type]
        with mock.patch.object(svc, "analyze_soon") as soon:
            svc.start()
        svc.stop()
        soon.assert_not_called()

    def test_closed_pinned_window_gets_a_card_that_can_unpin(self) -> None:
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication

        from iris.monitoring.screen_capture import CaptureResult
        from iris.ui.monitor.unified_monitor_panel import UnifiedMonitorPanel, _WindowSnap

        app = QApplication.instance() or QApplication([])
        panel = UnifiedMonitorPanel()
        panel._timer.stop()
        store = PinStore()
        store.pin("실시간 자막", 99)
        store.pin("빌드", 5)
        panel.set_pin_store(store)

        open_snap = _WindowSnap(_win("빌드", 5), CaptureResult(2, 2, bytes(12)))
        panel._render([open_snap], {})
        self.assertEqual(len(panel._thumbs), 2)

        closed = WindowInfo("실시간 자막", 0, 0, 0, 0, hwnd=0)
        with mock.patch(
            "iris.ui.monitor.unified_monitor_panel.focus_and_place"
        ) as place, mock.patch(
            "iris.ui.monitor.unified_monitor_panel.focus_window_by_hwnd"
        ) as focus:
            panel._focus_window(closed)
        place.assert_not_called()
        focus.assert_not_called()

        panel._toggle_pin(closed)
        self.assertEqual([p.title for p in store.list_pins()], ["빌드"])
        self.assertEqual(len(panel._thumbs), 1)
        del app

    def test_retries_soon_while_ollama_is_starting(self) -> None:
        store = PinStore()
        store.pin("빌드", 5)
        settings = SimpleNamespace(ollama_base_url="http://fake/v1")
        svc = PinnedMonitorService(store, settings, lambda: "")  # type: ignore[arg-type]
        retries: list[int] = []
        svc._retry_requested.disconnect()
        svc._retry_requested.connect(lambda: retries.append(1))
        down = (None, "Ollama에 연결하지 못했어요 (refused)")
        svc._started_at = pinned_monitor.time.monotonic()
        with mock.patch("iris.infrastructure.local_vision.resolve_vision_model", return_value=down):
            svc._analyze_all("")
            self.assertEqual(retries, [1])
            # 켠 지 오래됐으면 heartbeat 에 맡긴다 (Ollama 가 정말 꺼진 경우 10초마다 두드리지 않게)
            svc._started_at -= 600
            svc._analyze_all("")
        self.assertEqual(retries, [1])
