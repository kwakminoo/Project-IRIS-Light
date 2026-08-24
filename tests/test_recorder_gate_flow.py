"""Recorder poll 분기 — end/drop이 preroll return에 삼켜지지 않는지."""

from __future__ import annotations

from unittest import TestCase

from iris.audio.speech_gate import SpeechGate


def _route_gate_event(*, gate: SpeechGate, event: str, pcm: bytes, utterance: bytearray) -> tuple[str, bytearray]:
    """recorder._poll_audio gate 분기 미러 — end/drop은 반드시 처리."""
    if event == "start":
        return "started", bytearray(pcm)
    if event == "drop":
        return "dropped", bytearray()
    if gate.speaking or event == "end":
        utterance.extend(pcm)
        if event == "end":
            return "ended", utterance
        return "collecting", utterance
    return "preroll", utterance


class RecorderGateFlowTests(TestCase):
    def test_end_event_is_not_swallowed_after_gate_clears_speaking(self) -> None:
        gate = SpeechGate(speech_rms=0.02, start_frames=2, end_frames=2, min_speech_frames=2)
        utterance = bytearray()
        gate.feed(0.05)
        self.assertEqual(gate.feed(0.05), "start")
        gate.feed(0.05)
        gate.feed(0.001)
        event = gate.feed(0.001)
        self.assertEqual(event, "end")
        self.assertFalse(gate.speaking)
        action, utterance = _route_gate_event(gate=gate, event=event, pcm=b"pcm", utterance=utterance)
        self.assertEqual(action, "ended")
        self.assertEqual(bytes(utterance), b"pcm")

    def test_drop_event_reaches_drop_handler(self) -> None:
        gate = SpeechGate(speech_rms=0.02, start_frames=2, end_frames=2, min_speech_frames=4)
        utterance = bytearray(b"partial")
        self.assertEqual(gate.feed(0.08), "")
        self.assertEqual(gate.feed(0.08), "start")
        self.assertEqual(gate.feed(0.001), "")
        event = gate.feed(0.001)
        self.assertEqual(event, "drop")
        action, utterance = _route_gate_event(gate=gate, event=event, pcm=b"x", utterance=utterance)
        self.assertEqual(action, "dropped")
        self.assertEqual(bytes(utterance), b"")
