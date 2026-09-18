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
    from iris.infrastructure.api_model_meta import tool_support_label
    from iris.ui.chat.model_picker_menu import (
        BRAND_MIN_MODELS,
        PickerModel,
        _COLOR_MODEL_NO_TOOLS,
        _COLOR_MODEL_PRO,
        _COLOR_MODEL_UNKNOWN,
        picker_tier_color,
        split_picker_groups,
    )

    # 도구지원은 3-상태 — 미확정을 True로 낙관하지 않음
    assert tool_support_label("yes") == "도구 가능"
    assert tool_support_label("no") == "도구 미지원"
    assert tool_support_label("") == "도구 미확인"
    assert (
        picker_tier_color(PickerModel("u", "u", tool_support="unknown"))
        == _COLOR_MODEL_UNKNOWN
    )
    assert (
        picker_tier_color(PickerModel("x", "x", supports_tools=False))
        == _COLOR_MODEL_NO_TOOLS
    )
    assert (
        picker_tier_color(PickerModel("y", "y", requires_subscription=True))
        == _COLOR_MODEL_PRO
    )
    # 계층은 제공자 이름이 아니라 모델 수로만 결정됨 (연번 16 관련)
    gemini_many = [
        PickerModel(
            f"api:gm:models/gemini-{i}",
            f"Gemini · gemini-{i}",
            True,
            provider_name="Gemini",
            is_api=True,
        )
        for i in range(BRAND_MIN_MODELS)
    ]
    ollama, brands, singles = split_picker_groups(
        [
            PickerModel("a:cloud", "a", True),
            PickerModel(
                "api:oa:gpt-4o",
                "OpenAI · gpt-4o",
                True,
                provider_name="OpenAI",
                is_api=True,
            ),
            *gemini_many,
        ]
    )
    assert len(ollama) == 1
    assert list(brands) == ["gm"], brands  # Gemini는 이름이 아니라 개수로 묶임
    assert len(brands["gm"]) == BRAND_MIN_MODELS
    assert [m.provider_name for m in singles] == ["OpenAI"]  # 1개 제공자는 그대로 노출
    print("model picker tiers self-check ok")


if __name__ == "__main__":
    main()
