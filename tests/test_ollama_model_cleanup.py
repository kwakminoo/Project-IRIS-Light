"""Ollama 모델 정리 — API 모델 정리와 같은 제외 규칙."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from iris.infrastructure.ollama_client import (
    OllamaModelInfo,
    apply_ollama_cleanup,
    cleanup_verdict,
)
from iris.storage.database import Database
from iris.storage.model_prefs import (
    load_ollama_model_probes,
    ollama_cleanup_has_verdict,
    save_ollama_model_probe,
)


class OllamaCleanupVerdictTest(unittest.TestCase):
    def test_transient_stays_unverified(self) -> None:
        self.assertEqual(
            cleanup_verdict("unavailable", transient=True, capabilities=None, show_ok=False),
            ("unverified", "unknown"),
        )

    def test_subscription_is_excluded(self) -> None:
        self.assertEqual(
            cleanup_verdict("subscription", transient=False, capabilities=None, show_ok=False),
            ("unavailable", "unknown"),
        )

    def test_tools_from_capabilities(self) -> None:
        self.assertEqual(
            cleanup_verdict("ok", transient=False, capabilities=["completion", "tools"], show_ok=True),
            ("ok", "yes"),
        )
        self.assertEqual(
            cleanup_verdict("ok", transient=False, capabilities=["completion"], show_ok=True),
            ("ok", "no"),
        )

    def test_apply_keeps_unavailable(self) -> None:
        model = OllamaModelInfo(name="gemma:2b")
        kept_dead = apply_ollama_cleanup(model, {"state": "unavailable", "tool": "unknown"})
        self.assertEqual(kept_dead.availability, "unavailable")
        self.assertEqual(kept_dead.name, "gemma:2b")
        kept = apply_ollama_cleanup(model, {"state": "ok", "tool": "no"})
        self.assertFalse(kept.supports_tools)
        self.assertIs(apply_ollama_cleanup(model, None), model)

    def test_tier_order(self) -> None:
        from iris.infrastructure.ollama_client import model_list_tier

        usable = model_list_tier("gemma:7b", state="ok", tool="yes")
        unusable = model_list_tier("gemma:7b", state="unavailable", tool="unknown")
        unfit_embed = model_list_tier("bge-m3:latest", state="ok", tool="yes")
        unfit_tools = model_list_tier("qwen:7b", state="ok", tool="no")
        self.assertLess(usable[0], unusable[0])
        self.assertLess(unusable[0], unfit_embed[0])
        self.assertEqual(unfit_embed[0], unfit_tools[0])
        self.assertEqual(usable[1], "쓸 수 있음")
        self.assertEqual(unusable[1], "쓸 수 없음")
        self.assertEqual(unfit_embed[1], "적합하지 않음")

    def test_probe_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "t.db")
            try:
                self.assertFalse(ollama_cleanup_has_verdict(db))
                save_ollama_model_probe(db, "a", state="unverified", tool="unknown")
                self.assertFalse(ollama_cleanup_has_verdict(db))
                save_ollama_model_probe(db, "b", state="unavailable", tool="unknown")
                self.assertTrue(ollama_cleanup_has_verdict(db))
                probes = load_ollama_model_probes(db)
                self.assertEqual(probes["b"]["state"], "unavailable")
            finally:
                db._conn.close()


if __name__ == "__main__":
    unittest.main()
