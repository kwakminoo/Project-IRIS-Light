"""모델 콤보 tier 색/플래그 자체 점검."""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from iris.infrastructure.ollama_client import (
    OllamaModelInfo,
    probe_status_from_http_detail,
    supports_tools_capability,
)


def _pick_color(supports_tools: bool, requires_sub: bool) -> str:
    if requires_sub:
        return "pro"
    if not supports_tools:
        return "no_tools"
    return "default"


def main() -> None:
    assert supports_tools_capability(["tools"]) is True
    assert probe_status_from_http_detail("upgrade to pro") == "subscription"

    free_tools = OllamaModelInfo(name="a:cloud", supports_tools=True, requires_subscription=False)
    free_plain = OllamaModelInfo(name="b:cloud", supports_tools=False, requires_subscription=False)
    pro = OllamaModelInfo(name="c:cloud", supports_tools=True, requires_subscription=True)
    pro_plain = OllamaModelInfo(name="d:cloud", supports_tools=False, requires_subscription=True)

    assert _pick_color(free_tools.supports_tools, free_tools.requires_subscription) == "default"
    assert _pick_color(free_plain.supports_tools, free_plain.requires_subscription) == "no_tools"
    assert _pick_color(pro.supports_tools, pro.requires_subscription) == "pro"
    assert _pick_color(pro_plain.supports_tools, pro_plain.requires_subscription) == "pro"

    app = QApplication.instance() or QApplication(sys.argv)
    _ = app
    from iris.ui.chat import chat_panel as cp

    assert cp._COLOR_MODEL_DEFAULT.name() == "#38bdf8"
    assert cp._COLOR_MODEL_NO_TOOLS.name() == "#9ca3af"
    assert cp._COLOR_MODEL_PRO.name() == "#fca5a5"

    from iris.ui.settings import hud_dialog as hd

    assert callable(hd.run_hud_confirm)
    assert "IrisHudConfirm" in hd._confirm_qss(accent="#fca5a5")
    print("model picker tiers self-check ok")


if __name__ == "__main__":
    main()
