"""Control web.run_* registered; missing key → structured error (no hang)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from iris.system.control_surface import ActionRegistry, runs_off_ui_thread
from iris.ui.control_actions.web import register_web_actions


def main() -> None:
    assert runs_off_ui_thread("web.run_search") is True
    assert runs_off_ui_thread("web.run_extract") is True

    reg = ActionRegistry()
    register_web_actions(MagicMock(), reg)
    assert reg.spec("web.run_search") is not None
    assert reg.spec("web.run_extract") is not None
    assert reg.spec("web.run_search").confirm_required is False
    assert reg.spec("web.run_extract").confirm_required is False

    empty_keys = {
        "SERPAPI_API_KEY": "",
        "BRAVE_SEARCH_API_KEY": "",
        "TAVILY_API_KEY": "",
        "EXA_API_KEY": "",
        "FIRECRAWL_API_KEY": "",
        "PARALLEL_API_KEY": "",
        "KEENABLE_API_KEY": "",
        "SEARXNG_URL": "",
    }
    with patch(
        "iris.system.iris_web.load_search_api_keys", return_value=empty_keys
    ), patch("iris.system.iris_web.load_search_entries", return_value=[]):
        out = reg.invoke("web.run_search", {"query": "test"})
    assert out["ok"] is False, out
    assert out.get("error"), out
    # Must not import Hermes checkout tools.
    from pathlib import Path

    web_mod = Path(__file__).resolve().parent / "control_actions" / "web.py"
    text = web_mod.read_text(encoding="utf-8")
    assert "tools.web_tools" not in text
    print("web_run_actions ok", out.get("error")[:100])


if __name__ == "__main__":
    main()
