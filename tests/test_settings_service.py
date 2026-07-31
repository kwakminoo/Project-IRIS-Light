from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import TestCase

from iris.storage.user_profile import UserProfile
from iris.storage.voice_prefs import VoicePreferences
from iris.ui.settings import settings_service


class BuildProfileUpdateTests(TestCase):
    def setUp(self) -> None:
        self.base = UserProfile(name="tester")

    def test_custom_ide_without_exe_path_rejected(self) -> None:
        with self.assertRaises(ValueError):
            settings_service.build_profile_update(
                self.base,
                preferred_ide="custom",
                ide_exe_path="",
                ide_cli_path="",
                project_root="",
                parents_customized=False,
                project_parents=[],
            )

    def test_customized_empty_parents_rejected(self) -> None:
        with self.assertRaises(ValueError):
            settings_service.build_profile_update(
                self.base,
                preferred_ide="cursor",
                ide_exe_path="",
                ide_cli_path="",
                project_root="",
                parents_customized=True,
                project_parents=[],
            )

    def test_nonexistent_parent_dir_rejected(self) -> None:
        with self.assertRaises(ValueError):
            settings_service.build_profile_update(
                self.base,
                preferred_ide="cursor",
                ide_exe_path="",
                ide_cli_path="",
                project_root="",
                parents_customized=True,
                project_parents=["/no/such/path/xyz"],
            )

    def test_valid_input_builds_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = settings_service.build_profile_update(
                self.base,
                preferred_ide="cursor",
                ide_exe_path="",
                ide_cli_path="",
                project_root="",
                parents_customized=True,
                project_parents=[tmp],
            )
        self.assertEqual(profile.name, "tester")
        self.assertEqual(profile.preferred_ide, "cursor")
        self.assertEqual(profile.project_parents, [tmp])

    def test_not_customized_clears_parents(self) -> None:
        profile = settings_service.build_profile_update(
            self.base,
            preferred_ide="cursor",
            ide_exe_path="",
            ide_cli_path="",
            project_root="",
            parents_customized=False,
            project_parents=["/ignored"],
        )
        self.assertEqual(profile.project_parents, [])


class VoiceReferenceValidationTests(TestCase):
    def test_confirm_missing_audio_rejected_before_network_call(self) -> None:
        prefs = VoicePreferences(tts_reference_audio="", tts_reference_text="hi")
        with self.assertRaises(ValueError):
            settings_service.confirm_voice_reference("http://127.0.0.1:1", prefs)

    def test_ensure_hash_returns_cached_without_network_call(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".wav") as f:
            prefs = VoicePreferences(
                tts_reference_audio=f.name,
                tts_reference_text="hi",
                tts_voice_prompt_hash="cached-hash",
            )
            result = settings_service.ensure_voice_hash_for_test("http://127.0.0.1:1", prefs)
        self.assertEqual(result, "cached-hash")

    def test_ensure_hash_missing_reference_rejected(self) -> None:
        prefs = VoicePreferences(tts_reference_audio="", tts_reference_text="")
        with self.assertRaises(ValueError):
            settings_service.ensure_voice_hash_for_test("http://127.0.0.1:1", prefs)


class HermesSyncStatusTests(TestCase):
    def test_returns_status_text_without_raising(self) -> None:
        text = settings_service.load_hermes_sync_status_text()
        self.assertTrue(text.startswith("상태:"))
