"""PR4 기본 피치(+1.5)가 평소 TTS에 남지 않게."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from iris.storage.voice_prefs import VoicePreferences, load_voice_preferences


class VoicePitchDefaultTests(unittest.TestCase):
    def test_dataclass_default_is_zero(self) -> None:
        self.assertEqual(VoicePreferences().tts_pitch_semitones, 0.0)

    def test_legacy_one_point_five_is_reset(self) -> None:
        db = mock.Mock()
        db.get_preference.return_value = json.dumps({"tts_pitch_semitones": 1.5})
        prefs = load_voice_preferences(db)
        self.assertEqual(prefs.tts_pitch_semitones, 0.0)

    def test_intentional_other_pitch_is_kept(self) -> None:
        db = mock.Mock()
        db.get_preference.return_value = json.dumps({"tts_pitch_semitones": 3.0})
        prefs = load_voice_preferences(db)
        self.assertEqual(prefs.tts_pitch_semitones, 3.0)


if __name__ == "__main__":
    unittest.main()
