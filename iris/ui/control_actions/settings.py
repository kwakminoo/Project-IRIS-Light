"""설정 값과 설정 화면 컨트롤 액션."""

from __future__ import annotations

from iris.system.control_surface import (
    ActionRegistry,
)
from iris.ui.control_actions.hosts import SettingsHost

def register_settings_actions(window: SettingsHost, reg: ActionRegistry) -> None:
    from iris.ui.control_bindings import (
        _log,
        err_result,
        ok_result,
    )

    def ui_settings(_a: dict[str, Any]) -> dict[str, Any]:
        window._open_settings_dialog()
        _log(window, "ui.open_settings", True)
        return ok_result("ui.open_settings", {})

    def ui_profile(_a: dict[str, Any]) -> dict[str, Any]:
        window._open_user_profile_dialog()
        _log(window, "ui.open_user_profile", True)
        return ok_result("ui.open_user_profile", {})

    def ui_skills(_a: dict[str, Any]) -> dict[str, Any]:
        chat = getattr(window, "_chat", None)
        opener = getattr(chat, "_open_skills_dialog", None) if chat is not None else None
        if not callable(opener):
            return err_result("ui.open_skills", "skills dialog unavailable")
        opener()
        _log(window, "ui.open_skills", True)
        return ok_result("ui.open_skills", {})

    def ui_mcp(_a: dict[str, Any]) -> dict[str, Any]:
        chat = getattr(window, "_chat", None)
        opener = getattr(chat, "_open_mcp_dialog", None) if chat is not None else None
        if not callable(opener):
            return err_result("ui.open_mcp", "mcp dialog unavailable")
        opener()
        _log(window, "ui.open_mcp", True)
        return ok_result("ui.open_mcp", {})

    def settings_get(_a: dict[str, Any]) -> dict[str, Any]:
        from iris.infrastructure.agent_runtime import load_pinned_sha

        s = window._settings
        return ok_result(
            "settings.get",
            {
                "ollama_base_url": s.ollama_base_url,
                "ollama_model": s.ollama_model,
                "agent_required": True,
                "agent_version": load_pinned_sha(),
                "hermes_enabled": s.hermes_enabled,
            },
        )

    def settings_set(args: dict[str, Any]) -> dict[str, Any]:
        s = window._settings
        # 에이전트 URL·키·명령은 런타임 홈 .env / supervisor 소유. 설정 액션으로 받지 않음.
        blocked = ("hermes_api_key", "hermes_command", "hermes_base_url")
        for key in blocked:
            if key in args:
                return err_result(
                    "settings.set",
                    f"{key} is owned by Iris Agent runtime home — not editable via settings",
                )
        if "ollama_model" in args or "model" in args:
            return err_result("settings.set", "Choose a model directly in the model picker UI")
        changed: list[str] = []
        if "ollama_base_url" in args:
            s.ollama_base_url = str(args["ollama_base_url"] or "").strip() or s.ollama_base_url
            changed.append("ollama_base_url")
        # 에이전트는 도구 호출의 유일한 경로이므로 끌 수 없음. 조용히 무시하면
        # 모델이 자기 도구를 잃은 채 성공했다고 답하게 됨.
        if "hermes_enabled" in args and not bool(args["hermes_enabled"]):
            return err_result(
                "settings.set",
                "agent cannot be disabled — Iris Agent is required for tool calls",
            )
        window._status_header.set_model_name(s.model_name or s.ollama_model or "(unset)")
        window._refresh_hermes_health()
        _log(window, "settings.set", True)
        return ok_result("settings.set", {"changed": changed})

    reg.register("ui.open_settings", ui_settings, summary="Open Iris settings dialog")

    reg.register(
        "ui.open_user_profile",
        ui_profile,
        summary="Open user profile dialog",
    )

    reg.register(
        "ui.open_skills",
        ui_skills,
        summary="Open Iris Agent Skills manager dialog",
    )

    reg.register(
        "ui.open_mcp",
        ui_mcp,
        summary="Open Iris Agent MCP manager dialog",
    )

    reg.register(
        "settings.get",
        settings_get,
        summary="Get Ollama and Iris Agent version (no secret values)",
    )

    reg.register(
        "settings.set",
        settings_set,
        summary="Set Ollama settings; agent URL/key/command are not editable",
        risk="high",
        confirm_required=False,
    )
