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
        s = window._settings
        return ok_result(
            "settings.get",
            {
                "ollama_base_url": s.ollama_base_url,
                "ollama_model": s.ollama_model,
                "hermes_enabled": s.hermes_enabled,
                "hermes_command": s.hermes_command,
                "hermes_base_url": s.hermes_base_url,
                "hermes_api_key_set": bool(s.hermes_api_key),
            },
        )

    def settings_set(args: dict[str, Any]) -> dict[str, Any]:
        s = window._settings
        if "hermes_api_key" in args and not bool(args.get("confirm")):
            return err_result("settings.set", "confirm=true required to set hermes_api_key")
        changed: list[str] = []
        if "ollama_base_url" in args:
            s.ollama_base_url = str(args["ollama_base_url"] or "").strip() or s.ollama_base_url
            changed.append("ollama_base_url")
        if "ollama_model" in args or "model" in args:
            model = str(args.get("ollama_model") or args.get("model") or "").strip()
            if model:
                window._apply_selected_model(model, persist=True)
                changed.append("ollama_model")
        # Hermes는 도구 호출의 유일한 경로이므로 끌 수 없음. 조용히 무시하면
        # 모델이 자기 도구를 잃은 채 성공했다고 답하게 됨.
        if "hermes_enabled" in args and not bool(args["hermes_enabled"]):
            return err_result(
                "settings.set",
                "hermes_enabled cannot be disabled — Hermes is required for tool calls",
            )
        if "hermes_command" in args:
            s.hermes_command = str(args["hermes_command"] or "").strip() or s.hermes_command
            changed.append("hermes_command")
        if "hermes_base_url" in args:
            s.hermes_base_url = str(args["hermes_base_url"] or "").strip() or s.hermes_base_url
            changed.append("hermes_base_url")
        if "hermes_api_key" in args:
            s.hermes_api_key = str(args.get("hermes_api_key") or "")
            changed.append("hermes_api_key")
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
        summary="Open Hermes Skills manager dialog",
    )

    reg.register(
        "ui.open_mcp",
        ui_mcp,
        summary="Open Hermes MCP manager dialog",
    )

    reg.register("settings.get", settings_get, summary="Get Ollama/Hermes connection settings (no secret values)")

    reg.register(
        "settings.set",
        settings_set,
        summary="Set Ollama/Hermes settings; hermes_api_key needs confirm=true",
        risk="high",
        confirm_required=False,  # key path checks confirm itself
    )
