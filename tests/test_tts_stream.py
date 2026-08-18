from __future__ import annotations

from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from iris.audio.pcm_stream import (
    encode_event,
    parse_event_line,
    should_open_speakers,
    start_bytes,
)
from services.voice_runtime.tts_stream import (
    custom_speaker_name,
    normalize_engine,
    resolve_tone_ref_file,
    sovits_tts_payload,
)


class PcmBufferTests(TestCase):
    def test_waits_for_start_ms(self) -> None:
        need = start_bytes(24000, 320)
        self.assertEqual(need, int(24000 * 2 * 0.32))
        self.assertFalse(should_open_speakers(need - 2, 24000, stream_ended=False))
        self.assertTrue(should_open_speakers(need, 24000, stream_ended=False))

    def test_opens_early_when_stream_ends(self) -> None:
        self.assertTrue(should_open_speakers(20, 24000, stream_ended=True))
        self.assertFalse(should_open_speakers(0, 24000, stream_ended=True))

    def test_ndjson_roundtrip(self) -> None:
        raw = encode_event({"type": "start", "sample_rate": 24000})
        event = parse_event_line(raw.decode("utf-8"))
        self.assertEqual(event["type"], "start")
        self.assertEqual(event["sample_rate"], 24000)


class EngineRoutingTests(TestCase):
    def test_unknown_engine_falls_back_to_qwen(self) -> None:
        self.assertEqual(normalize_engine("nope"), "qwen")
        self.assertEqual(normalize_engine("qwen_custom"), "qwen_custom")

    def test_tone_speaker_names(self) -> None:
        self.assertEqual(
            custom_speaker_name("iris", "caution", tone_routing=True),
            "iris_caution",
        )
        self.assertEqual(custom_speaker_name("iris", "caution", tone_routing=False), "iris")

    def test_sovits_payload_is_korean(self) -> None:
        payload = sovits_tts_payload("안녕하세요", r"C:\ref.wav", "기준 대본")
        self.assertEqual(payload["text_lang"], "ko")
        self.assertEqual(payload["prompt_lang"], "ko")
        self.assertEqual(payload["ref_audio_path"], r"C:\ref.wav")

    def test_resolve_tone_ref_file(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            nested = root / "2차" / "briefing"
            nested.mkdir(parents=True)
            wav = nested / "a.wav"
            wav.write_bytes(b"RIFF")
            self.assertEqual(resolve_tone_ref_file(str(wav), str(root)), str(wav))
            rel = str(Path("2차") / "briefing" / "a.wav")
            self.assertEqual(resolve_tone_ref_file(rel, str(root)), str(wav))
            self.assertEqual(resolve_tone_ref_file("missing.wav", str(root)), "")


class MockStreamTests(TestCase):
    def test_mock_mode_emits_start_chunk_end(self) -> None:
        from services.voice_runtime.model_manager import VoiceModelManager
        from services.voice_runtime.tts_service import TTSService
        from services.voice_runtime.tts_stream import StreamSynthRequest, iter_pcm_events
        from services.voice_runtime import tts_stream as stream_mod

        service = TTSService(VoiceModelManager())
        with patch.object(stream_mod, "CONFIG") as cfg:
            cfg.mock_mode = True
            events = list(iter_pcm_events(service, StreamSynthRequest(text="안녕")))
        kinds = [e.get("type") for e in events]
        self.assertEqual(kinds[0], "start")
        self.assertIn("chunk", kinds)
        self.assertEqual(kinds[-1], "end")
        self.assertTrue(events[1].get("pcm_b64"))
