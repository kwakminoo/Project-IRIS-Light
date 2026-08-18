from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from iris.audio.pcm_stream import (
    DEFAULT_START_MS,
    MAX_START_MS,
    MIN_START_MS,
    clamp_start_ms,
    should_open_speakers,
    start_bytes,
)
from iris.audio.tts_pipeline import TtsSentencePump, should_start_tts_synth


class TtsPrefetchDecisionTests(TestCase):
    def test_starts_first_chunk(self) -> None:
        self.assertTrue(
            should_start_tts_synth(
                synthesizing=False, pending_count=3, ready_count=0
            )
        )

    def test_keeps_gpu_busy_when_ready_already_queued(self) -> None:
        self.assertTrue(
            should_start_tts_synth(
                synthesizing=False, pending_count=2, ready_count=3
            )
        )

    def test_waits_when_already_synthesizing(self) -> None:
        self.assertFalse(
            should_start_tts_synth(
                synthesizing=True, pending_count=2, ready_count=0
            )
        )


class TtsSentencePumpTests(TestCase):
    def test_first_complete_sentence_emits_immediately(self) -> None:
        pump = TtsSentencePump()
        sentence = "안녕하세요, 요청하신 내용을 바로 확인해드리겠습니다."
        self.assertEqual(pump.feed(sentence), [sentence])

    def test_short_fragment_merges_with_following_sentence(self) -> None:
        pump = TtsSentencePump(min_chars=16)
        self.assertEqual(pump.feed("네. "), [])
        out = pump.feed("이제 요청하신 내용을 자세히 안내해드리겠습니다.")
        self.assertEqual(out, ["네. 이제 요청하신 내용을 자세히 안내해드리겠습니다."])

    def test_long_first_clause_splits_at_safe_korean_word_boundary(self) -> None:
        pump = TtsSentencePump(min_chars=12, first_target_chars=30, first_max_chars=42)
        text = "이 문장은 충분히 길기 때문에 안전한 공백 경계에서 자연스럽게 분리되어야 합니다"
        out = pump.feed(text)
        self.assertEqual(len(out), 1)
        self.assertLessEqual(len(out[0]), 42)
        self.assertTrue(text.startswith(out[0]))
        self.assertEqual(text[len(out[0])], " ")

    def test_clause_boundary_is_preferred_after_first_chunk(self) -> None:
        pump = TtsSentencePump(
            min_chars=10,
            later_target_chars=24,
            later_max_chars=60,
        )
        self.assertTrue(pump.feed("첫 번째 문장은 충분히 길어서 바로 재생할 수 있습니다."))
        out = pump.feed("다음 절은 쉼표에서 자연스럽게, 그리고 뒤의 설명도 계속 이어집니다")
        self.assertEqual(out, ["다음 절은 쉼표에서 자연스럽게,"])

    def test_soft_deadline_never_emits_tiny_or_midword_fragment(self) -> None:
        pump = TtsSentencePump(
            min_chars=12,
            first_target_chars=80,
            first_max_chars=90,
            soft_flush_ms=300,
        )
        pump.feed("문장 종결 없이도 안전한 공백 경계에서", now=0.0)
        self.assertEqual(pump.poll(now=0.299), [])
        self.assertEqual(pump.poll(now=0.301), ["문장 종결 없이도 안전한 공백"])

        tiny = TtsSentencePump(min_chars=12, soft_flush_ms=300)
        tiny.feed("아주 짧게", now=0.0)
        self.assertEqual(tiny.poll(now=0.5), [])

    def test_flush_keeps_last_text_once_without_duplicates(self) -> None:
        pump = TtsSentencePump()
        first = "첫 번째 문장은 충분히 길어서 즉시 재생할 수 있습니다."
        tail = "마지막 문장은 끝맺음 없이 남아 있습니다"
        emitted = pump.feed(first)
        self.assertEqual(emitted, [first])
        self.assertEqual(pump.feed(tail), [])
        self.assertEqual(pump.flush(), [tail])
        self.assertEqual(pump.flush(), [])

    def test_english_numbers_and_pronunciation_map_are_preserved(self) -> None:
        pump = TtsSentencePump()
        out = pump.feed("IRIS API 버전 3.2를 지금 바로 점검하겠습니다.")
        self.assertEqual(out, ["아이리스 에이피아이 버전 3.2를 지금 바로 점검하겠습니다."])

    def test_partial_code_url_and_path_never_escape_normalization(self) -> None:
        pump = TtsSentencePump(min_chars=12)
        first = "먼저 충분히 긴 안내 문장을 말씀드리겠습니다. "
        self.assertEqual(pump.feed(first + "```python\nprint('secret')"), [first.strip()])
        self.assertEqual(
            pump.feed(
                "\n```\nhttps://example.com/very/long/path "
                "C:\\temp\\report.txt **API** 관련 다음 설명을 이어가겠습니다."
            ),
            [],
        )
        spoken = " ".join(pump.flush())
        self.assertIn("다음 설명", spoken)
        self.assertIn("에이피아이", spoken)
        self.assertNotIn("print", spoken)
        self.assertNotIn("secret", spoken)
        self.assertNotIn("https://", spoken)
        self.assertNotIn("example.com", spoken)
        self.assertNotIn("C:\\temp", spoken)

    def test_partial_url_prefix_is_held_until_the_token_is_complete(self) -> None:
        pump = TtsSentencePump(min_chars=12, first_target_chars=24, first_max_chars=72)
        out = pump.feed("링크 정보는 충분히 길게 안내드리지만 https:")
        self.assertEqual(out, ["링크 정보는 충분히 길게 안내드리지만"])
        self.assertEqual(pump.feed("//example.com/path 입니다."), [])
        self.assertNotIn("https", " ".join(pump.flush()))


class PcmBufferTests(TestCase):
    def test_real_time_default_and_clamp(self) -> None:
        self.assertEqual(DEFAULT_START_MS, 100)
        self.assertEqual(start_bytes(24000, DEFAULT_START_MS), 4800)
        self.assertEqual(clamp_start_ms(0), MIN_START_MS)
        self.assertEqual(clamp_start_ms(99999), MAX_START_MS)
        self.assertEqual(clamp_start_ms("bad"), DEFAULT_START_MS)

    def test_short_stream_opens_when_session_ends(self) -> None:
        need = start_bytes(24000, 100)
        self.assertFalse(should_open_speakers(need - 2, 24000, stream_ended=False, start_ms=100))
        self.assertTrue(should_open_speakers(need, 24000, stream_ended=False, start_ms=100))
        self.assertTrue(should_open_speakers(20, 24000, stream_ended=True, start_ms=100))

    def test_stop_clears_an_unopened_session_buffer(self) -> None:
        from iris.audio.pcm_player import PcmPlayer

        player = PcmPlayer(start_ms=100)
        player.feed(b"\0" * 100)
        self.assertTrue(player.is_busy())
        player.stop()
        self.assertFalse(player.is_busy())

    def test_backpressure_keeps_pcm_in_arrival_order(self) -> None:
        from iris.audio.pcm_player import PcmPlayer

        class PartialIo:
            def __init__(self) -> None:
                self.written = bytearray()
                self._writes = 0

            def write(self, raw: bytes) -> int:
                self._writes += 1
                if self._writes == 2:
                    return 0
                count = 2 if self._writes == 1 else len(raw)
                self.written.extend(raw[:count])
                return count

        player = PcmPlayer(start_ms=100)
        io = PartialIo()
        player._opened = True
        player._io = io
        player._write(b"abcd")
        player.feed(b"efgh")

        self.assertEqual(bytes(io.written), b"abcdefgh")
        self.assertEqual(bytes(player._buf), b"")

    def test_pcm_player_applies_enabled_ai_voice_effect(self) -> None:
        from iris.audio.pcm_player import PcmPlayer

        class CollectingIo:
            def __init__(self) -> None:
                self.written = bytearray()

            def write(self, raw: bytes) -> int:
                self.written.extend(raw)
                return len(raw)

        player = PcmPlayer(start_ms=100)
        io = CollectingIo()
        player._opened = True
        player._io = io
        player.set_voice_effect(enabled=True, intensity=0.35)
        raw = b"\x10\x27" * 256
        player.feed(raw)

        self.assertEqual(len(io.written), len(raw))
        self.assertNotEqual(bytes(io.written), raw)
        player.stop()


class TtsStreamWorkerTests(TestCase):
    def test_cancel_closes_active_http_stream(self) -> None:
        from unittest.mock import Mock

        from iris.audio.workers import TTSStreamWorker

        worker = TTSStreamWorker(
            runtime_url="http://test",
            text="안녕하세요",
            payload={"engine": "qwen"},
        )
        response = Mock()
        worker._set_stream_response(response)
        worker.request_cancel()

        self.assertTrue(worker._is_cancelled())
        response.close.assert_called_once_with()

    def test_response_opened_after_cancel_is_closed_too(self) -> None:
        from unittest.mock import Mock

        from iris.audio.workers import TTSStreamWorker

        worker = TTSStreamWorker(
            runtime_url="http://test",
            text="안녕하세요",
            payload={"engine": "qwen"},
        )
        worker.request_cancel()
        response = Mock()
        worker._set_stream_response(response)

        response.close.assert_called_once_with()

    def test_stream_worker_emits_format_pcm_then_finished(self) -> None:
        from iris.audio.workers import TTSStreamWorker

        pcm_a, pcm_b = b"\x01\x02", b"\x03\x04"

        class FakeClient:
            def __init__(self, **_kwargs: object) -> None:
                pass

            def iter_tts_speech_stream(self, **_kwargs: object):
                yield {"type": "start", "sample_rate": 24000}
                yield {"type": "chunk", "pcm_b64": base64.b64encode(pcm_a).decode()}
                yield {"type": "chunk", "pcm_b64": base64.b64encode(pcm_b).decode()}
                yield {"type": "end"}

        events: list[tuple[str, object]] = []
        worker = TTSStreamWorker(
            runtime_url="http://test",
            text="안녕하세요",
            payload={"engine": "qwen"},
        )
        worker.started_fmt.connect(lambda rate: events.append(("start", rate)))
        worker.chunk.connect(lambda pcm: events.append(("chunk", pcm)))
        worker.finished_ok.connect(lambda: events.append(("finished", None)))
        worker.failed.connect(lambda message: events.append(("failed", message)))

        with patch("iris.audio.workers.VoiceRuntimeClient", FakeClient):
            worker.run()

        self.assertEqual(
            events,
            [
                ("start", 24000),
                ("chunk", pcm_a),
                ("chunk", pcm_b),
                ("finished", None),
            ],
        )


class StreamingScheduleTests(TestCase):
    def test_finished_worker_starts_next_before_pcm_session_can_end(self) -> None:
        from iris.ui.window.main_window import MainWindow

        calls: list[str] = []

        class FakeWindow:
            _tts_job_id = 7
            _tts_worker = object()

            class _Pcm:
                def flush_start(self) -> None:
                    calls.append("flush")

            _pcm_player = _Pcm()

            def _start_next_tts_segment(self) -> None:
                calls.append("next")

            def _maybe_end_pcm_session(self) -> None:
                calls.append("end")

        fake = FakeWindow()
        MainWindow._on_tts_stream_finished(fake, 7)
        self.assertIsNone(fake._tts_worker)
        self.assertEqual(calls, ["flush", "next", "end"])

    def test_late_pcm_from_cancelled_job_is_ignored(self) -> None:
        from iris.ui.window.main_window import MainWindow

        calls: list[str] = []

        class FakeWindow:
            _tts_job_id = 8

            def _mark_tts_perf(self, _name: str) -> None:
                calls.append("perf")

        MainWindow._on_pcm_chunk(FakeWindow(), b"late", 7)
        self.assertEqual(calls, [])

    def test_failed_job_cancels_worker_and_rejects_late_pcm(self) -> None:
        from iris.ui.window.main_window import MainWindow

        calls: list[str] = []

        class Worker:
            def isRunning(self) -> bool:
                return True

            def request_cancel(self) -> None:
                calls.append("cancel")

        class Stoppable:
            def stop(self) -> None:
                calls.append("stop")

        class Header:
            def set_tts_status(self, value: str) -> None:
                calls.append(value)

        class Activity:
            def append_instant_line(self, _line: str) -> None:
                calls.append("activity")

        class Chat:
            def fallback_typing_if_waiting_for_tts(self) -> None:
                calls.append("fallback")

        class FakeWindow:
            _tts_job_id = 7
            _tts_worker = Worker()
            _tts_cancelled_workers: list[object] = []
            _tts_queue: list[str] = []
            _tts_input_finished = False
            _tts_pump = object()
            _tts_pump_timer = Stoppable()
            _tts_active_play = False
            _tts_pcm_ending = False
            _tts_pcm_job_id = 7
            _tts_runtime_ready = True
            _media_player = Stoppable()
            _pcm_player = Stoppable()
            _status_header = Header()
            _live_activity = Activity()
            _chat = Chat()
            _tts_active_msg_id = ""

            def _set_tts_orb_warmup(self, _active: bool) -> None:
                calls.append("orb")

            def _resume_mic_after_tts(self) -> None:
                calls.append("resume")

            def _mark_tts_perf(self, _name: str) -> None:
                calls.append("perf")

        fake = FakeWindow()
        MainWindow._on_tts_failed(fake, "bad", 7)
        self.assertEqual(fake._tts_job_id, 8)
        self.assertEqual(calls.count("cancel"), 1)
        MainWindow._on_pcm_chunk(fake, b"late", 7)
        self.assertNotIn("perf", calls)

    def test_tts_validation_does_not_start_runtime_on_ui_thread(self) -> None:
        from iris.ui.window.main_window import MainWindow

        class FakeWindow:
            _voice_prefs = SimpleNamespace(
                tts_engine="qwen",
                tts_use_voice_profile=True,
                tts_custom_model_path="",
                gpt_sovits_url="",
                tts_reference_audio="",
                tts_reference_text="",
            )

            def _ensure_voice_runtime(self) -> bool:
                raise AssertionError("runtime startup must use bootstrap worker")

        self.assertTrue(MainWindow._tts_can_start(FakeWindow(), ""))

    def test_stale_bootstrap_result_is_not_adopted_after_settings_change(self) -> None:
        from iris.ui.window.main_window import MainWindow

        calls: list[str] = []

        class FakeWindow:
            _tts_bootstrap_worker = object()
            _tts_runtime_ready = True
            _voice_prefs = SimpleNamespace(
                tts_model="model-b",
                voice_runtime_url="http://b",
                voice_runtime_mock=False,
            )

            def _bootstrap_matches_current(self, model: str, url: str, mock: bool) -> bool:
                return False

            def _schedule_tts_runtime_bootstrap(self) -> None:
                calls.append("schedule")

        fake = FakeWindow()
        MainWindow._on_tts_bootstrap_done(
            fake,
            {"running": True, "accepted": True},
            "model-a",
            "http://a",
            False,
        )
        self.assertFalse(fake._tts_runtime_ready)
        self.assertEqual(calls, ["schedule"])


class SettingsPreviewCancellationTests(TestCase):
    def test_stop_invalidates_late_preview_pcm(self) -> None:
        from iris.ui.settings.settings_dialog import SettingsDialog

        calls: list[object] = []

        class Worker:
            def isRunning(self) -> bool:
                return True

            def request_cancel(self) -> None:
                calls.append("cancel")

        class Player:
            def stop(self) -> None:
                calls.append("stop")

            def feed(self, pcm: bytes) -> None:
                calls.append(pcm)

        class FakeDialog:
            _settings_tts_job_id = 4
            _settings_tts_worker = Worker()
            _settings_tts_cancelled_workers: list[object] = []
            _settings_tts_bootstrap_worker = None
            _settings_tts_cancelled_bootstrap_workers: list[object] = []
            _preview_player = Player()

        fake = FakeDialog()
        self.assertFalse(SettingsDialog._stop_voice_playback(fake, announce=False))
        SettingsDialog._on_settings_tts_chunk(fake, b"late", 4)
        self.assertEqual(fake._settings_tts_job_id, 5)
        self.assertEqual(calls, ["cancel", "stop"])
        self.assertEqual(len(fake._settings_tts_cancelled_workers), 1)
