"""ChatPanel ↔ model_favorite_prefs wire self-check (no full MainWindow)."""

from __future__ import annotations

import inspect
import sys
import tempfile
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from iris.storage.database import Database
from iris.storage.model_favorite_prefs import (
    load_model_favorites,
    toggle_model_favorite,
)
from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.chat.model_picker_menu import ModelBrandDialog, PickerModel


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)

    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "fav_wire.db")
        assert load_model_favorites(db) == []
        assert toggle_model_favorite(db, "api:nv:foo") is True
        assert load_model_favorites(db) == ["api:nv:foo"]

        panel = ChatPanel()
        assert panel._model_favorites == set()
        panel.set_model_favorites(load_model_favorites(db))
        assert panel._model_favorites == {"api:nv:foo"}

        emitted: list[str] = []
        panel.model_favorite_toggled.connect(emitted.append)

        def persist_like_main_window(runtime: str) -> None:
            toggle_model_favorite(db, runtime)
            panel.set_model_favorites(load_model_favorites(db))

        panel.model_favorite_toggled.connect(persist_like_main_window)
        panel._on_model_favorite_toggled("api:nv:foo")
        assert emitted == ["api:nv:foo"]
        assert load_model_favorites(db) == []
        assert panel._model_favorites == set()

        panel._on_model_favorite_toggled("llama3.2:latest")
        assert load_model_favorites(db) == ["llama3.2:latest"]
        assert panel._model_favorites == {"llama3.2:latest"}

        panel.set_model_favorites(["  a  ", "", "b", "a"])
        assert panel._model_favorites == {"a", "b"}

        open_src = inspect.getsource(ChatPanel._open_model_picker_menu)
        assert "favorites=favs" in open_src or "favorites=self._model_favorites" in open_src
        assert "favorite_toggled.connect(self._on_model_favorite_toggled)" in open_src

        brand_src = inspect.getsource(ChatPanel._show_brand_dialog)
        assert "favorites=self._model_favorites" in brand_src
        assert "favorite_toggled.connect(self._on_model_favorite_toggled)" in brand_src

        m = PickerModel("api:nv:foo", "foo", is_api=True, provider_name="NVIDIA")
        panel.set_model_favorites(["api:nv:foo"])
        dlg = ModelBrandDialog("NVIDIA", [m], favorites=panel._model_favorites)
        assert "api:nv:foo" in dlg._favorites
        dlg.close()
        panel.close()
        db.close()

    # Keep app referenced so Qt does not warn on early GC of QApplication.
    _ = app
    print("model_favorites_wire ok")


if __name__ == "__main__":
    main()
