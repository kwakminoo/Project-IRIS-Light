from __future__ import annotations

from typing import Any

from iris.browser.registry import command_specs, parse_command
from iris.browser.session import get_browser_session
from iris.system.control_surface import ActionRegistry
from iris.ui.control_actions.hosts import BrowserHost


def register_browser_actions(window: BrowserHost, reg: ActionRegistry) -> None:
    from iris.ui.control_bindings import _append_activity, _call_on_ui, _log, err_result, ok_result

    session = get_browser_session()
    session.set_ui_call(lambda fn: _call_on_ui(window, fn))

    def _surface():
        ide = window._ensure_iris_ide_window()
        return ide.show_browser()

    def _apply_host(host: str) -> None:
        ide = window._ensure_iris_ide_window()
        ide.apply_browser_view_host(host)

    session.set_surface_provider(_surface)
    session.set_host_applier(_apply_host)

    def _handle(action_name: str, args: dict[str, Any]) -> dict[str, Any]:
        wire = dict(args or {})
        wire.setdefault("action", action_name)
        if action_name != "browser.invoke" and "command" not in wire:
            kind = action_name.split(".", 1)[-1]
            wire["command"] = kind
        try:
            cmd = parse_command(wire)
        except (ValueError, TypeError) as exc:
            return err_result(action_name, str(exc))
        result = session.execute(cmd)
        _log(window, action_name, result.ok)
        if result.ok:
            _append_activity(window, f"browser: {result.command_kind}")
            return ok_result(action_name, result.to_control_dict())
        return err_result(action_name, result.detail or "browser command failed", result.to_control_dict())

    def browser_invoke(a: dict[str, Any]) -> dict[str, Any]:
        return _handle("browser.invoke", a)

    reg.register(
        "browser.invoke",
        browser_invoke,
        summary="Run a browser command via BrowserSession.execute",
        risk="medium",
    )

    for spec in command_specs():
        name = spec.control_name

        def _make(action: str):
            def handler(a: dict[str, Any]) -> dict[str, Any]:
                return _handle(action, a)

            return handler

        reg.register(
            name,
            _make(name),
            summary=spec.summary,
            risk=spec.risk,
        )
