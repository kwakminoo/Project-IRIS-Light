"""Self-check: AI Hub Ollama panel wires catalog + pull + CLI paste + library link."""

from __future__ import annotations

import inspect
from pathlib import Path


def main() -> None:
    from iris.infrastructure.local_model_catalog import (
        OLLAMA_LIBRARY_URL,
        RECOMMENDED_LOCAL_MODELS,
        group_by_brand,
        parse_ollama_cli,
        with_install_flags,
    )

    assert RECOMMENDED_LOCAL_MODELS
    assert OLLAMA_LIBRARY_URL == "https://ollama.com/library"
    flagged = with_install_flags(RECOMMENDED_LOCAL_MODELS, set())
    assert len(flagged) == len(RECOMMENDED_LOCAL_MODELS)
    assert all(not installed for _, installed in flagged)
    grouped = group_by_brand(RECOMMENDED_LOCAL_MODELS)
    assert grouped
    assert parse_ollama_cli("ollama pull gemma4:e2b") == "gemma4:e2b"

    src_path = Path(__file__).resolve().parent / "ollama_panel.py"
    src = src_path.read_text(encoding="utf-8")
    assert "모델 더 보기" in src
    assert "OLLAMA_LIBRARY_URL" in src
    assert "from iris.infrastructure.local_vision import" in src
    assert "pull_model" in src
    assert "delete_model" in src
    assert "AiOllamaPanel" in src
    assert "설치" in src
    assert "parse_ollama_cli" in src
    assert "AiHubOllamaTerm" in src
    assert "AiHubOllamaDeleteTerm" in src
    assert "_installed_host" in src
    assert "사용" in src
    assert "삭제" in src
    assert "model_use_requested" in src
    assert "neon_cyan" in src
    assert "group_by_brand" not in src
    assert "QLabel(brand_id)" not in src
    assert "QDesktopServices.openUrl" in src
    assert "models_changed" in src
    assert "AlignHCenter" in src
    # Installed section must appear after the install `_term` in source order.
    term_i = src.index("AiHubOllamaTerm")
    installed_i = src.index("_installed_host")
    delete_term_i = src.index("AiHubOllamaDeleteTerm")
    assert term_i < installed_i < delete_term_i

    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    from iris.config.settings import Settings
    from iris.ui.ai_hub.ollama_panel import AiOllamaPanel
    from iris.ui.ai_hub import ai_hub_dialog as hub_mod

    assert inspect.isclass(AiOllamaPanel)
    panel = AiOllamaPanel(Settings())
    assert panel.title() == "Ollama (로컬)"
    assert hasattr(panel, "models_changed")
    assert hasattr(panel, "model_use_requested")
    assert hasattr(panel, "_cli_input")
    assert hasattr(panel, "_install_btn")
    assert hasattr(panel, "_term")
    assert hasattr(panel, "_installed_host")
    assert hasattr(panel, "_delete_term")
    assert panel._term.objectName() == "AiHubOllamaTerm"
    assert panel._delete_term.objectName() == "AiHubOllamaDeleteTerm"
    assert not panel._term.isVisible()
    assert not panel._delete_term.isVisible()
    # Stop background list worker before teardown (slot abort if signals land after delete).
    panel._stop_workers()
    panel.deleteLater()
    app.processEvents()

    hub_src = inspect.getsource(hub_mod)
    assert "AiOllamaPanel" in hub_src
    assert "self._ollama" in hub_src
    assert "ollama_models_changed" in hub_src
    assert "model_use_requested" in hub_src
    assert "shutdown" in hub_src

    mw_path = Path(__file__).resolve().parents[1] / "window" / "main_window.py"
    mw_src = mw_path.read_text(encoding="utf-8")
    assert "ollama_models_changed" in mw_src
    assert "_open_ai_hub_dialog" in mw_src
    assert "model_use_requested.connect" in mw_src
    assert "_on_hub_model_use" in mw_src
    assert "_hub_use_pending" in mw_src
    from iris.ui.window import main_window as mw_mod

    hub_use_src = inspect.getsource(mw_mod.MainWindow._on_hub_model_use)
    assert "select_model_silent" in hub_use_src
    assert "_apply_selected_model" in hub_use_src

    print("ai_hub ollama_panel ok")


if __name__ == "__main__":
    main()
