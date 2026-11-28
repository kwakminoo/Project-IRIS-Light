"""FFC-03 Unit 5 — residual Hermes STRIP closes with honest Native paths.

Fails when:
- execute_code does not resolve to shell/project terminal path
- execute_code dual-emits a second schema
- cronjob_manage schema / routine.manage missing
- connections.status leaks secret-looking fields
- computer_use omits unsupported raw_desktop
- image_generate / text_to_speech invent payload bytes
- memory umbrella leaves strip while memory_search grant is gone

Run:
  .venv\\Scripts\\python.exe -m iris.infrastructure._check_ffc03_residual_absorb
"""

from __future__ import annotations

from types import SimpleNamespace

from iris.infrastructure.absorbed_tool_aliases import (
    INTERNAL_ALIASES,
    resolve_action,
    strip_only_names,
)
from iris.infrastructure.speak_capability import (
    PHASE4_ALLOWLIST,
    engine_tool_name,
    engine_tool_schemas,
)
from iris.system.control_surface import ActionRegistry
from iris.ui.control_actions.computer import register_computer_actions
from iris.ui.control_actions.connections import register_connections_actions
from iris.ui.control_actions.provider_status import register_provider_status_actions
from iris.ui.control_actions.routine import register_routine_actions


_SECRET_FRAGMENTS = (
    "token",
    "api_key",
    "apikey",
    "secret",
    "password",
    "authorization",
    "bearer",
    "credential",
)


def _assert_no_secret_keys(obj: object, *, path: str = "$") -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            low = str(key).lower()
            assert not any(frag in low for frag in _SECRET_FRAGMENTS), (path, key)
            _assert_no_secret_keys(value, path=f"{path}.{key}")
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            _assert_no_secret_keys(item, path=f"{path}[{idx}]")


def _check_execute_code_alias() -> None:
    assert INTERNAL_ALIASES.get("execute_code") == "terminal"
    assert resolve_action("execute_code", "home") == "shell.run"
    assert resolve_action("execute_code", "ide_companion") == "project.run"
    home = {str(row["name"]) for row in engine_tool_schemas("home")}
    assert "execute_code" not in home
    assert "terminal" in home


def _check_cronjob_schema() -> None:
    grant = PHASE4_ALLOWLIST.grant("routine.manage")
    assert grant is not None
    assert engine_tool_name("routine.manage") == "cronjob_manage"
    home = {str(row["name"]) for row in engine_tool_schemas("home")}
    assert "cronjob_manage" in home
    assert "routine_manage" not in home
    params = dict(grant.parameters or {})
    op = (params.get("properties") or {}).get("operation") or {}
    assert set(op.get("enum") or []) == {
        "create",
        "list",
        "update",
        "delete",
        "run",
    }


def _check_connections_no_secrets() -> None:
    reg = ActionRegistry()
    register_connections_actions(reg)
    result = reg.invoke("connections.status", {})
    assert result.get("ok") is True, result
    payload = result.get("result") or {}
    _assert_no_secret_keys(payload)
    assert "mcp_servers" in payload
    assert "gateway" in payload


def _check_computer_unsupported_desktop() -> None:
    reg = ActionRegistry()
    register_computer_actions(reg)
    result = reg.invoke("computer.surfaces", {})
    assert result.get("ok") is True, result
    payload = result.get("result") or {}
    unsupported = payload.get("unsupported") or []
    assert "raw_desktop" in unsupported, payload
    supported_ids = {row.get("id") for row in (payload.get("supported") or []) if isinstance(row, dict)}
    assert {"browser", "ide", "emulator", "learning"} <= supported_ids, supported_ids
    assert payload.get("observe_only") is True


def _check_image_tts_no_fake_payload() -> None:
    window = SimpleNamespace(_tts_runtime_ready=False, _voice_prefs=SimpleNamespace(tts_enabled=False))
    reg = ActionRegistry()
    register_provider_status_actions(window, reg)

    image = reg.invoke("image.status", {})
    assert image.get("ok") is True, image
    img = image.get("result") or {}
    assert img.get("payload") is None, img
    assert img.get("status") in {"not_installed", "unsupported", "needs_approval"}, img
    assert not img.get("image") and not img.get("bytes") and not img.get("audio")

    tts = reg.invoke("voice.tts_status", {})
    assert tts.get("ok") is True, tts
    voice = tts.get("result") or {}
    assert voice.get("payload") is None, voice
    assert voice.get("status") in {"not_installed", "needs_approval", "unsupported"}, voice
    assert not voice.get("audio") and not voice.get("pcm") and not voice.get("bytes")

    home = {str(row["name"]) for row in engine_tool_schemas("home")}
    assert "image_generate" in home
    assert "text_to_speech" in home
    assert engine_tool_name("image.status") == "image_generate"
    assert engine_tool_name("voice.tts_status") == "text_to_speech"


def _check_memory_umbrella_strip() -> None:
    strip = strip_only_names()
    assert "memory" in strip
    assert resolve_action("memory", "home") is None
    assert PHASE4_ALLOWLIST.grant("memory.search") is not None
    home = {str(row["name"]) for row in engine_tool_schemas("home")}
    assert "memory_search" in home
    assert "memory" not in home


def _check_routine_manage_dispatcher() -> None:
    """manage is a dispatcher — list path must not invent side effects without db."""

    class _Win:
        _db = None

        def _sync_iris_wiki(self, **_kwargs: object) -> None:
            raise AssertionError("list must not sync wiki")

        def _run_routine_now(self, *_a: object, **_k: object) -> bool:
            raise AssertionError("list must not run")

    # Without db, list_routines will fail — register still wires manage.
    reg = ActionRegistry()
    # Minimal stub: only exercise unknown-op refusal without touching storage.
    register_routine_actions(_Win(), reg)
    bad = reg.invoke("routine.manage", {"operation": "nope"})
    assert bad.get("ok") is False, bad


def main() -> None:
    _check_execute_code_alias()
    _check_cronjob_schema()
    _check_connections_no_secrets()
    _check_computer_unsupported_desktop()
    _check_image_tts_no_fake_payload()
    _check_memory_umbrella_strip()
    _check_routine_manage_dispatcher()

    home_n = len(engine_tool_schemas("home"))
    print(
        "ffc03_residual_absorb ok",
        f"home_n={home_n}",
        f"strip={sorted(strip_only_names())}",
    )


if __name__ == "__main__":
    main()
