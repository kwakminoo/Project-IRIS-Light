"""Model picker open path must pass favorites and keep frameless-safe parent."""

from __future__ import annotations

import inspect
import re
import sys

from PyQt6.QtWidgets import QApplication

from iris.ui.chat import chat_panel as cp
from iris.ui.chat.model_picker_menu import (
    ModelBrandDialog,
    ModelPickerMenu,
    PickerModel,
    split_picker_groups,
)


def _assert_favorites_kw(src: str, name: str) -> None:
    # Nested ) in kwargs (e.g. bool(ollama)) breaks [^)]* — scan a window after the call.
    match = re.search(rf"{re.escape(name)}\s*\(", src)
    assert match, f"{name} not called"
    window = src[match.start() : match.start() + 500]
    assert "favorites=" in window, f"{name} missing favorites="


def main() -> None:
    open_src = inspect.getsource(cp.ChatPanel._open_model_picker_menu)
    brand_src = inspect.getsource(cp.ChatPanel._show_brand_dialog)
    on_brand_src = inspect.getsource(cp.ChatPanel._on_open_brand)
    combined = "\n".join((open_src, brand_src, on_brand_src))

    for name in ("split_picker_groups", "ModelPickerMenu", "ModelBrandDialog"):
        _assert_favorites_kw(combined, name)

    assert "favorite_toggled.connect" in open_src
    assert "favorite_toggled.connect" in brand_src

    # Modal dialog must not parent frameless MainWindow (same class as QFileDialog abort).
    assert "parent=None" in brand_src or re.search(
        r"ModelBrandDialog\s*\(\s*[^,]*,\s*[^,]*,\s*None\b",
        brand_src,
        flags=re.DOTALL,
    ), "ModelBrandDialog parent must be None"
    assert "self.window()" not in brand_src

    models = [
        PickerModel("gemma4:latest", "gemma4:latest"),
        PickerModel(
            "api:nv:meta/llama-3.1-8b-instruct",
            "NVIDIA · llama",
            is_api=True,
            provider_name="NVIDIA",
        ),
    ]
    fav = {"api:nv:meta/llama-3.1-8b-instruct"}
    local, ollama, brands, singles = split_picker_groups(models, favorites=fav)
    brand_rows = [
        (pid, next((m.provider_name for m in items if m.provider_name), pid), len(items))
        for pid, items in brands.items()
    ]

    app = QApplication.instance() or QApplication(sys.argv)
    menu = ModelPickerMenu(
        local=local,
        has_ollama=bool(ollama),
        brands=brand_rows,
        singles=singles,
        favorites=fav,
        parent=None,
    )
    assert hasattr(menu, "favorite_toggled")
    dlg = ModelBrandDialog("LOCAL MODEL", local, None, hint="test", favorites=fav)
    assert hasattr(dlg, "favorite_toggled")
    dlg.close()
    menu.close()
    _ = app
    print("model_picker_open self-check ok")


if __name__ == "__main__":
    main()
