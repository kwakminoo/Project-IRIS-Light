"""Model picker favorites survive reload and stay visible in brand dialogs."""

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
from iris.ui.chat.model_picker_menu import ModelBrandDialog, PickerModel, split_picker_groups


APP = QApplication.instance() or QApplication(sys.argv)


class ModelFavoritesRestoreTests(unittest.TestCase):
    def test_favorites_persist_across_database_reopen(self):
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

    def test_one_api_model_is_still_under_its_brand(self):
        model = PickerModel("api:nv:model", "model", is_api=True, provider_name="NVIDIA")
        _local, _ollama, brands, singles = split_picker_groups([model])
        self.assertEqual(list(brands), ["nv"])
        self.assertEqual(singles, [])

    def test_favorites_sort_first_within_brand(self):
        first = PickerModel("api:nv:alpha", "alpha", is_api=True, provider_name="NVIDIA")
        favorite = PickerModel("api:nv:zeta", "zeta", is_api=True, provider_name="NVIDIA")
        _local, _ollama, brands, _singles = split_picker_groups(
            [first, favorite], favorites={favorite.runtime}
        )
        self.assertEqual([m.runtime for m in brands["nv"]], [favorite.runtime, first.runtime])

    def test_brand_star_emits_without_selecting_and_panel_forwards(self):
        model = PickerModel("api:nv:model", "model", is_api=True, provider_name="NVIDIA")
        panel = ChatPanel()
        panel.set_model_favorites([model.runtime])
        forwarded = []
        panel.model_favorite_toggled.connect(forwarded.append)
        dialog = ModelBrandDialog("NVIDIA", [model], favorites=panel._model_favorites)
        chosen = []
        toggled = []
        dialog.model_chosen.connect(chosen.append)
        dialog.favorite_toggled.connect(toggled.append)
        star = dialog.findChild(QToolButton, "ModelFavoriteStar")
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
