"""Model picker favorites survive reload and stay visible in brand dialogs."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QToolButton

from iris.storage.database import Database
from iris.storage.model_favorite_prefs import load_model_favorites, toggle_model_favorite
from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.chat.model_picker_menu import (
    BRAND_MIN_MODELS,
    ModelBrandDialog,
    PickerModel,
    split_picker_groups,
)


APP = QApplication.instance() or QApplication(sys.argv)


class ModelFavoritesRestoreTests(unittest.TestCase):
    def test_favorites_persist_across_database_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "iris.db"
            db = Database(path)
            self.assertTrue(toggle_model_favorite(db, "api:nv:model"))
            db.close()
            db = Database(path)
            self.assertEqual(load_model_favorites(db), ["api:nv:model"])
            self.assertFalse(toggle_model_favorite(db, "api:nv:model"))
            self.assertEqual(load_model_favorites(db), [])
            db.close()

    def test_one_api_model_stays_in_singles_until_brand_min(self) -> None:
        # Product contract: remote API needs BRAND_MIN_MODELS+ before brand fold.
        model = PickerModel("api:nv:model", "model", is_api=True, provider_name="NVIDIA")
        _local, _ollama, brands, singles = split_picker_groups([model])
        self.assertEqual(brands, {})
        self.assertEqual([m.runtime for m in singles], ["api:nv:model"])
        many = [
            PickerModel(
                f"api:nv:m{i}",
                f"m{i}",
                is_api=True,
                provider_name="NVIDIA",
            )
            for i in range(BRAND_MIN_MODELS)
        ]
        _local, _ollama, brands, singles = split_picker_groups(many)
        self.assertEqual(list(brands), ["nv"])
        self.assertEqual(len(brands["nv"]), BRAND_MIN_MODELS)
        self.assertEqual(singles, [])

    def test_favorites_sort_first_within_brand(self) -> None:
        many = [
            PickerModel(
                f"api:nv:m{i}",
                f"m{i:02d}",
                is_api=True,
                provider_name="NVIDIA",
            )
            for i in range(BRAND_MIN_MODELS)
        ]
        favorite = many[-1]
        _local, _ollama, brands, _singles = split_picker_groups(
            many, favorites={favorite.runtime}
        )
        self.assertEqual(brands["nv"][0].runtime, favorite.runtime)

    def test_brand_star_emits_without_selecting_and_panel_forwards(self) -> None:
        model = PickerModel("api:nv:model", "model", is_api=True, provider_name="NVIDIA")
        panel = ChatPanel()
        panel.set_model_favorites([model.runtime])
        forwarded: list[str] = []
        panel.model_favorite_toggled.connect(forwarded.append)
        dialog = ModelBrandDialog(
            "NVIDIA", [model], None, favorites=panel._model_favorites
        )
        chosen: list[str] = []
        toggled: list[str] = []
        dialog.model_chosen.connect(chosen.append)
        dialog.favorite_toggled.connect(toggled.append)
        star = dialog.findChild(QToolButton, "ModelFavoriteStar")
        self.assertIsNotNone(star)
        self.assertEqual(star.text(), "★")
        star.click()
        self.assertEqual(toggled, [model.runtime])
        self.assertEqual(chosen, [])
        panel._on_model_favorite_toggled(model.runtime)
        self.assertEqual(forwarded, [model.runtime])
        dialog.close()
        panel.close()


if __name__ == "__main__":
    unittest.main()
