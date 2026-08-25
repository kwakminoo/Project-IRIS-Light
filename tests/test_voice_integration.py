from __future__ import annotations

import json
import tempfile
import wave
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

from iris.storage.database import Database
from iris.storage.voice_prefs import (
    VOICE_PREFS_KEY,
    VoicePreferences,
    default_voice_data_dir,
    load_voice_preferences,
    resolve_saved_voice_data_dir,
    save_voice_preferences,
)


class VoicePrefsTests(TestCase):
    def test_save_and_load_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db = Database(Path(td) / "t.db")
            prefs = VoicePreferences(
                stt_enabled=True,
                stt_model="base",
                stt_language="auto",
                stt_speech_rms=0.035,
                voice_barge_in_enabled=False,
                voice_wake_word_enabled=True,
                voice_wake_words="아이리스,Iris",
                voice_followup_window_sec=15,
                tts_enabled=True,
                tts_mode="manual",
                tts_reference_audio=r"C:\tmp\ref.wav",
                tts_reference_text="hello",
                tts_ai_voice_fx_enabled=False,
                tts_ai_voice_fx_intensity=0.55,
                voice_runtime_mock=False,
                voice_data_dir=r"C:\voice",
            )
            save_voice_preferences(db, prefs)
            loaded = load_voice_preferences(db)
            self.assertTrue(loaded.stt_enabled)
            self.assertEqual(loaded.stt_model, "base")
            self.assertEqual(loaded.stt_language, "auto")
            self.assertAlmostEqual(loaded.stt_speech_rms, 0.035)
            self.assertFalse(loaded.voice_barge_in_enabled)
            self.assertTrue(loaded.voice_wake_word_enabled)
            self.assertEqual(loaded.voice_wake_words, "아이리스,Iris")
            self.assertEqual(loaded.voice_followup_window_sec, 15)
            self.assertEqual(loaded.tts_mode, "manual")
            self.assertEqual(loaded.tts_reference_text, "hello")
            self.assertEqual(loaded.tts_engine, "qwen")
            self.assertEqual(loaded.tts_custom_speaker, "iris")
            self.assertFalse(loaded.tts_ai_voice_fx_enabled)
            self.assertAlmostEqual(loaded.tts_ai_voice_fx_intensity, 0.55)
            self.assertFalse(loaded.voice_runtime_mock)
            self.assertEqual(loaded.voice_data_dir, r"C:\voice")
            db._conn.close()

    def test_legacy_missing_dir_maps_to_default(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db = Database(Path(td) / "t.db")
            gone = str(Path(td) / "1차 아이리스 녹음")
            save_voice_preferences(db, VoicePreferences(voice_data_dir=gone))
            loaded = load_voice_preferences(db)
            self.assertEqual(loaded.voice_data_dir, default_voice_data_dir())
            db._conn.close()

    def test_existing_custom_dir_is_kept(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            custom = Path(td) / "my-voice"
            custom.mkdir()
            self.assertEqual(resolve_saved_voice_data_dir(str(custom)), str(custom))
            missing = str(Path(td) / "no-such-folder")
            self.assertEqual(resolve_saved_voice_data_dir(missing), missing)

    def test_legacy_preferences_enable_strong_ai_voice_fx(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db = Database(Path(td) / "t.db")
            db.set_preference(VOICE_PREFS_KEY, json.dumps({"tts_enabled": True}))
            loaded = load_voice_preferences(db)
            self.assertTrue(loaded.tts_ai_voice_fx_enabled)
            self.assertAlmostEqual(loaded.tts_ai_voice_fx_intensity, 0.75)
            db._conn.close()

    def test_ai_voice_fx_intensity_is_clamped(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db = Database(Path(td) / "t.db")
            db.set_preference(
                VOICE_PREFS_KEY,
                json.dumps({"tts_ai_voice_fx_enabled": "off", "tts_ai_voice_fx_intensity": 9}),
            )
            loaded = load_voice_preferences(db)
            self.assertFalse(loaded.tts_ai_voice_fx_enabled)
            self.assertEqual(loaded.tts_ai_voice_fx_intensity, 1.0)
            db._conn.close()


class VoiceRuntimeClientTests(TestCase):
    def test_health_ok(self) -> None:
        from iris.audio.voice_runtime_client import VoiceRuntimeClient

        payload = json.dumps({"status": "ok", "pid": 1, "mock_mode": True}).encode("utf-8")
        fake = MagicMock()
        fake.read.return_value = payload
        fake.__enter__ = MagicMock(return_value=fake)
        fake.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=fake):
            h = VoiceRuntimeClient().health()
        self.assertEqual(h.status, "ok")
        self.assertTrue(h.mock_mode)

    def test_error_path(self) -> None:
        from iris.audio.voice_runtime_client import VoiceRuntimeClient, VoiceRuntimeError
        import urllib.error

        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("down"),
        ):
            with self.assertRaises(VoiceRuntimeError):
                VoiceRuntimeClient().health()

    def test_missing_reference_audio(self) -> None:
        from iris.audio.voice_runtime_client import VoiceRuntimeClient, VoiceRuntimeError

        client = VoiceRuntimeClient()
        with self.assertRaises(VoiceRuntimeError):
            client.voice_prepare(
                ref_audio_path=str(Path(tempfile.gettempdir()) / "no-such-iris-ref.wav"),
                ref_text="x",
            )


class VoiceRuntimeShutdownTests(TestCase):
    def test_manager_calls_shutdown(self) -> None:
        from iris.audio.voice_runtime_manager import VoiceRuntimeProcessManager

        mgr = VoiceRuntimeProcessManager(iris_root=Path("."))
        with patch.object(mgr._client, "shutdown") as shutdown:
            mgr.shutdown(timeout_sec=0.1)
            shutdown.assert_called_once()


class VoiceRuntimeVenvResolveTests(TestCase):
    def test_venv_python_accepts_unix_bin(self) -> None:
        from iris.audio.voice_runtime_manager import VoiceRuntimeProcessManager

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            unix = root / ".venv-voice" / "bin" / "python"
            unix.parent.mkdir(parents=True)
            unix.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
            unix.chmod(0o755)
            mgr = VoiceRuntimeProcessManager(iris_root=root)
            self.assertEqual(mgr._venv_python(), unix)

    def test_venv_python_accepts_windows_scripts(self) -> None:
        from iris.audio.voice_runtime_manager import VoiceRuntimeProcessManager

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            win = root / ".venv-voice" / "Scripts" / "python.exe"
            win.parent.mkdir(parents=True)
            win.write_bytes(b"MZ")
            mgr = VoiceRuntimeProcessManager(iris_root=root)
            self.assertEqual(mgr._venv_python(), win)

    def test_resolve_python_falls_back_to_host_for_mock(self) -> None:
        from iris.audio.voice_runtime_manager import VoiceRuntimeProcessManager
        import sys

        with tempfile.TemporaryDirectory() as td:
            mgr = VoiceRuntimeProcessManager(iris_root=Path(td))
            with patch.object(mgr, "_host_can_run_mock", return_value=True):
                resolved = mgr._resolve_python(mock_mode=True)
            self.assertEqual(resolved, Path(sys.executable))

    def test_resolve_python_bootstraps_when_missing(self) -> None:
        from iris.audio.voice_runtime_manager import VoiceRuntimeProcessManager

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake_py = root / "bootstrapped-python"
            fake_py.write_text("x", encoding="utf-8")
            mgr = VoiceRuntimeProcessManager(iris_root=root)
            with patch.object(mgr, "_host_can_run_mock", return_value=False):
                with patch.object(mgr, "_bootstrap_venv", return_value=fake_py) as boot:
                    resolved = mgr._resolve_python(mock_mode=False)
            boot.assert_called_once_with(include_stt=True)
            self.assertEqual(resolved, fake_py)


class ChatInsertInputTests(TestCase):
    def test_insert_appends_not_overwrite(self) -> None:
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        from iris.ui.chat.chat_panel import ChatPanel

        panel = ChatPanel()
        panel.set_input_text("hello")
        panel.insert_input_text("world")
        self.assertEqual(panel.current_input_text(), "hello world")
        panel.insert_input_text("again")
        self.assertEqual(panel.current_input_text(), "hello world again")
        self.assertIsNotNone(app)


class TtsQueueOrderTests(TestCase):
    def test_long_text_queue_order(self) -> None:
        from iris.audio.text_normalizer import split_tts_sentences

        text = "First sentence here. Second sentence follows. Third sentence ends."
        parts = split_tts_sentences(text, max_chars=40, min_chars=4)
        self.assertGreaterEqual(len(parts), 2)
        joined = " ".join(parts)
        self.assertIn("First", joined)
        self.assertIn("Third", joined)
        self.assertLess(joined.find("First"), joined.find("Third"))


class TextNormalizerEdgeTests(TestCase):
    def test_strips_tool_and_code(self) -> None:
        from iris.audio.text_normalizer import normalize_tts_text

        fence = chr(96) * 3
        text = (
            "thinking: plan\n"
            "tool call: search\n"
            f"{fence}python\nprint(1)\n{fence}\n"
            "Normal answer here. API ready.\n"
            "https://example.com\n"
        )
        out = normalize_tts_text(text)
        self.assertIn("Normal answer", out)
        self.assertIn("\uc5d0\uc774\ud53c\uc544\uc774", out)  # 에이피아이
        self.assertNotIn("print", out)
        self.assertNotIn("https://", out)
        self.assertNotIn("thinking", out.lower())


class RecommendRankTests(TestCase):
    def test_recommend_prefers_near_nine_seconds(self) -> None:
        import math
        import struct

        from services.voice_runtime.voice_dataset import (
            analyze_voice_file,
            recommend_reference_samples,
        )

        def write_wav(path: Path, seconds: float) -> None:
            sr = 16000
            frames = int(seconds * sr)
            with wave.open(str(path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sr)
                data = bytearray()
                for i in range(frames):
                    value = int(10000 * math.sin(2.0 * math.pi * 220.0 * (i / sr)))
                    data.extend(struct.pack("<h", value))
                wf.writeframes(bytes(data))

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            items = []
            for sec in (3.0, 9.0, 20.0):
                p = root / f"s{sec}.wav"
                write_wav(p, sec)
                items.append(
                    analyze_voice_file(
                        p,
                        transcript="hello",
                        language="ko",
                        language_probability=0.9,
                    )
                )
            picks = recommend_reference_samples(items, top_k=1)
            self.assertEqual(len(picks), 1)
            self.assertAlmostEqual(picks[0].duration, 9.0, delta=0.2)
