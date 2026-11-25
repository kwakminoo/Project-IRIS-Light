from __future__ import annotations

from typing import Any

from iris.browser.observation import looks_sensitive_browser_act, pack_hermes_result
from iris.browser.registry import command_specs, parse_command
from iris.browser.session import get_browser_session
from iris.browser.stale_ref import plan_stale_ref_recovery
from iris.browser.types import (
    BrowserResult,
    Click,
    PageNode,
    Scroll,
    Snapshot,
    TypeText,
    ViewHost,
)
from iris.system.control_surface import ActionRegistry
from iris.ui.control_actions.hosts import BrowserHost


def register_browser_actions(window: BrowserHost, reg: ActionRegistry) -> None:
    from iris.ui.control_bindings import (
        _append_activity,
        _call_on_ui_unbounded,
        _log,
        err_result,
        ok_result,
    )

    session = get_browser_session()
    # ponytail: 3s marshal returns None while WebEngine create keeps running.
    session.set_ui_call(lambda fn: _call_on_ui_unbounded(window, fn))

    def _surface():
        return window.show_browser_workspace()

    def _apply_host(host: ViewHost | str) -> None:
        window.apply_browser_view_host(host)

    session.set_surface_provider(_surface)
    session.set_host_applier(_apply_host)

    def _handle(action_name: str, args: dict[str, Any]) -> dict[str, Any]:
        # Agent/tool Control path only. UI panel sets Actor.HUMAN via session.execute.
        wire = dict(args or {})
        wire.pop("source", None)
        wire.setdefault("action", action_name)
        if action_name != "browser.invoke" and "command" not in wire:
            kind = action_name.split(".", 1)[-1]
            wire["command"] = kind
        try:
            cmd = parse_command(wire)
        except (ValueError, TypeError) as exc:
            return err_result(action_name, str(exc))
        approved_sensitive = False
        if looks_sensitive_browser_act(action_name, wire, session.snapshot()):
            spec = reg.spec(action_name)
            if spec is None:
                return err_result(action_name, "human confirm required")
            if not reg.ask_human(spec, wire):
                return err_result(action_name, "cancelled")
            approved_sensitive = True
        ref = str(wire.get("ref") or "").strip()
        intent = session.intent_node_for_ref(ref) if ref else None
        result = session.execute(cmd)
        if (
            (not result.ok)
            and result.detail == "stale_ref"
            and ref
            and isinstance(cmd, (Click, TypeText, Scroll))
        ):
            session.execute(Snapshot())
            fresh = session.snapshot()

            def _new_sensitive(node: PageNode) -> bool:
                probe = dict(wire)
                probe["ref"] = node.ref
                return looks_sensitive_browser_act(action_name, probe, fresh)

            plan = plan_stale_ref_recovery(
                intent=intent,
                fresh=fresh,
                approved_sensitive=approved_sensitive,
                new_is_sensitive=_new_sensitive,
            )
            if plan.action == "retry" and plan.new_ref:
                retry_wire = dict(wire)
                retry_wire["ref"] = plan.new_ref
                try:
                    retry_cmd = parse_command(retry_wire)
                except (ValueError, TypeError) as exc:
                    return err_result(action_name, str(exc))
                # One retry only — never loop on a second stale_ref.
                result = session.execute(retry_cmd)
            else:
                result = BrowserResult(
                    False,
                    result.command_kind,
                    fresh,
                    detail=plan.detail or "needs_reapproval",
                )
        _log(window, action_name, result.ok)
        payload = pack_hermes_result(result)
        if result.ok:
            _append_activity(window, f"browser: {result.command_kind}")
            return ok_result(action_name, payload)
        return err_result(action_name, result.detail or "browser command failed", payload)

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
