import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iris.storage.api_providers import (
    API_PROVIDERS_KEY,
    ApiProvider,
    load_api_providers,
    provider_is_selectable,
    save_api_providers,
)
from iris.storage.database import Database


class ApiProviderSecretTests(unittest.TestCase):
    def test_save_encrypts_and_legacy_plaintext_migrates(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "api.db")
            encrypt = lambda value: "test-enc:" + value[::-1] if value else ""
            decrypt = lambda value: value.removeprefix("test-enc:")[::-1] if value else ""
            with patch("iris.storage.api_providers.encrypt_secret", side_effect=encrypt), patch(
                "iris.storage.api_providers.decrypt_secret", side_effect=decrypt
            ):
                provider = ApiProvider(name="Groq", api_key="gsk-secret")
                save_api_providers(db, [provider])
                raw = db.get_preference(API_PROVIDERS_KEY, "")
                self.assertNotIn("gsk-secret", raw)
                self.assertNotIn('"api_key"', raw)
                self.assertEqual(load_api_providers(db)[0].api_key, "gsk-secret")

                legacy = [{"id": "old", "name": "Old", "api_key": "plain-secret"}]
                db.set_preference(API_PROVIDERS_KEY, json.dumps(legacy))
                self.assertEqual(load_api_providers(db)[0].api_key, "plain-secret")
                migrated = db.get_preference(API_PROVIDERS_KEY, "")
                self.assertNotIn("plain-secret", migrated)
                self.assertNotIn('"api_key"', migrated)
                self.assertIn("api_key_enc", migrated)
            db._conn.close()

    def test_picker_requires_enabled_url_models_and_healthy_status(self):
        provider = ApiProvider(
            name="Demo", base_url="https://example.test/v1", models=["m"], status="ok"
        )
        self.assertTrue(provider_is_selectable(provider))
        provider.status = "partial"
        self.assertTrue(provider_is_selectable(provider))
        provider.status = "error"
        self.assertFalse(provider_is_selectable(provider))
        provider.status = "ok"
        provider.models = []
        self.assertFalse(provider_is_selectable(provider))


if __name__ == "__main__":
    unittest.main()
