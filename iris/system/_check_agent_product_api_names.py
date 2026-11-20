"""PR-B1/B2/B3 — product API names are agent_*/iris_agent_*, not hermes_*.

Canonical defs must exist under the new names. Product modules must not keep
legacy ``def hermes_*`` path/API surfaces (no long-lived aliases).

PR-B3: product modules must not reference Settings ``.hermes_*`` attrs or pass
``hermes_*=`` kwargs. Control HTTP emits/accepts ``agent_enabled`` only
(no ``hermes_enabled`` dual-key).

E1/E1b include gateway public ``is_/ensure_/restart_/start_/stop_*`` rename
and ``is_iris_agent_syncable_model``. Thin ``hermes_*`` shims are gone.

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_agent_product_api_names
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

# (module path relative to repo, forbidden def name)
_FORBIDDEN_DEFS = (
    # PR-B1
    ("iris/runtime/agent_local_gate.py", "hermes_owns_local_intents"),
    ("iris/system/iris_agent_update.py", "apply_hermes_update"),
    ("iris/system/iris_agent_soul_sync.py", "hermes_soul_path"),
    # PR-B2 — product path helpers
    ("iris/system/iris_agent_control_sync.py", "hermes_home"),
    ("iris/system/iris_agent_control_sync.py", "hermes_config_path"),
    ("iris/system/iris_agent_control_sync.py", "hermes_skills_iris_control_dir"),
    # A1 — ControlSync public helpers
    ("iris/system/iris_agent_control_sync.py", "ensure_hermes_disabled_terminal"),
    ("iris/system/iris_agent_control_sync.py", "read_hermes_disabled_toolsets"),
    ("iris/system/iris_agent_control_sync.py", "verify_hermes_terminal_disabled"),
    ("iris/system/iris_agent_control_sync.py", "ensure_hermes_api_server_computer_use"),
    ("iris/system/iris_agent_control_sync.py", "read_hermes_api_server_toolsets"),
    ("iris/system/iris_agent_control_sync.py", "verify_hermes_api_server_computer_use"),
    ("iris/system/iris_agent_control_sync.py", "ensure_hermes_stdio_dead_check_patch"),
    ("iris/system/iris_agent_control_sync.py", "verify_hermes_stdio_dead_check"),
    ("iris/system/github_extension_install.py", "hermes_home"),
    # Unit2 absorb — credentials / search / login-warm / update prompt
    ("iris/infrastructure/iris_agent_credentials.py", "load_hermes_dotenv"),
    ("iris/infrastructure/iris_agent_credentials.py", "is_weak_hermes_api_key"),
    ("iris/infrastructure/external_api_keys.py", "apply_hermes_search_backend"),
    ("iris/storage/iris_agent_login_warm_prefs.py", "load_hermes_login_warm"),
    ("iris/storage/iris_agent_login_warm_prefs.py", "save_hermes_login_warm"),
    ("iris/ui/settings/settings_service.py", "load_hermes_sync_status_text"),
    ("iris/ui/chat/skill_mcp_dialogs.py", "hermes_root"),
    ("iris/system/iris_agent_gateway.py", "hermes_runtime_report"),
    ("iris/system/iris_agent_install.py", "hermes_python_range"),
    ("iris/system/iris_agent_install.py", "hermes_install_lock"),
    # E1 — gateway public API iris_agent_* (migrate callers then delete)
    ("iris/system/iris_agent_gateway.py", "is_hermes_gateway_running"),
    ("iris/system/iris_agent_gateway.py", "is_hermes_trampoline_failure"),
    ("iris/system/iris_agent_gateway.py", "is_hermes_cli_missing_failure"),
    ("iris/system/iris_agent_gateway.py", "is_hermes_gateway_dep_missing_failure"),
    ("iris/system/iris_agent_gateway.py", "ensure_hermes_gateway_running"),
    ("iris/system/iris_agent_gateway.py", "restart_hermes_gateway"),
    ("iris/system/iris_agent_gateway.py", "start_hermes_gateway"),
    # E1b — leftover public APIs
    ("iris/system/iris_agent_gateway.py", "stop_hermes_gateway"),
    ("iris/infrastructure/iris_agent_client.py", "is_hermes_syncable_model"),
)

# Attr / kwarg scrape — product must use agent_* only.
_HERMES_ATTR = re.compile(
    r"\.(hermes_enabled|hermes_command|hermes_base_url|hermes_api_key)\b"
)
_HERMES_KWARG = re.compile(
    r"\b(hermes_enabled|hermes_command|hermes_base_url|hermes_api_key)\s*="
)
_RESOLVE_OLD = re.compile(r"\bresolve_hermes_api_key\b")
# Control / MainWindow product path — Iris-only agent surface.
_LEGACY_ONLINE = re.compile(
    r"\b(_use_hermes_backend|_hermes_online|_refresh_hermes_health)\b"
)
_LEGACY_STATE_KEY = re.compile(r"[\"']hermes_online[\"']")
_LEGACY_ONLINE_KW = re.compile(r"\bhermes_online\s*=")

_SCRAPE_ALLOWLIST = frozenset(
    {
        # Thin shims / gateway / old module names (later units).
        "iris/system/iris_agent_gateway.py",
        "iris/infrastructure/iris_agent_credentials.py",  # resolve_* thin alias only
    }
)

_SCRAPE_SKIP_DIR_PARTS = frozenset(
    {
        "__pycache__",
    }
)


def _is_thin_hermes_shim(rel: str) -> bool:
    name = Path(rel).name
    return name.startswith("hermes_") and name.endswith(".py")


def _is_self_check(rel: str) -> bool:
    return Path(rel).name.startswith("_check_")


def _product_py_files() -> list[Path]:
    iris = _ROOT / "iris"
    out: list[Path] = []
    for path in iris.rglob("*.py"):
        if any(part in _SCRAPE_SKIP_DIR_PARTS for part in path.parts):
            continue
        out.append(path)
    return sorted(out)


def _def_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def check_forbidden_defs_gone() -> None:
    hits: list[str] = []
    for rel, name in _FORBIDDEN_DEFS:
        path = _ROOT / rel
        assert path.is_file(), path
        if name in _def_names(path):
            hits.append(f"{rel}: still defines {name}")
    assert not hits, "legacy product API defs remain:\n" + "\n".join(hits)


def check_new_names_exist() -> None:
    from iris.runtime.agent_local_gate import agent_owns_local_intents
    from iris.system.iris_agent_soul_sync import agent_soul_path
    from iris.system.iris_agent_update import apply_iris_agent_update

    assert agent_owns_local_intents(True) is True
    assert agent_owns_local_intents(False) is False
    params = list(inspect.signature(agent_owns_local_intents).parameters)
    assert params == ["agent_enabled"], params

    assert callable(apply_iris_agent_update)
    assert callable(agent_soul_path)

    import iris.runtime.agent_local_gate as gate
    import iris.system.iris_agent_soul_sync as soul
    import iris.system.iris_agent_update as upd

    for mod, banned in (
        (gate, "hermes_owns_local_intents"),
        (upd, "apply_hermes_update"),
        (soul, "hermes_soul_path"),
    ):
        assert not hasattr(mod, banned), f"{mod.__name__} still exports {banned}"

    from iris.infrastructure.agent_runtime import iris_agent_home
    from iris.system import iris_agent_control_sync as sync
    from iris.system import github_extension_install as ghext

    assert callable(sync.agent_config_path)
    assert callable(sync.agent_skills_dir)
    assert callable(sync.repo_skills_iris_agent_dir)
    assert sync.iris_agent_home is iris_agent_home
    assert sync.agent_config_path().name == "config.yaml"
    # Canonical skills home is iris-agent (not iris-control-only).
    assert sync.agent_skills_dir().name == "iris-agent"
    assert "skills" in sync.agent_skills_dir().parts
    assert sync.agent_skills_legacy_dir().name == "iris-control"
    assert sync.repo_skills_iris_agent_dir().name == "iris-agent"
    assert sync.repo_skills_iris_agent_dir().is_dir()
    ensure_src = Path(_ROOT / "iris/system/iris_agent_control_sync.py").read_text(
        encoding="utf-8"
    )
    assert 'skills" / "iris-agent"' in ensure_src or "skills' / 'iris-agent'" in ensure_src
    assert "def agent_skills_dir" in ensure_src
    assert "migrate_legacy_agent_skills" in ensure_src
    # Canonical helper must return iris-agent; legacy helper may still name iris-control.
    assert (
        'return _resolved_home(home) / "skills" / "iris-agent"' in ensure_src
        or "return _resolved_home(home) / 'skills' / 'iris-agent'" in ensure_src
    )
    # ensure_skills_installed must write via agent_skills_dir (canonical), not legacy-only.
    ensure_fn = inspect.getsource(sync.ensure_skills_installed)
    assert "agent_skills_dir" in ensure_fn
    assert "migrate_legacy_agent_skills" in ensure_fn

    for mod, banned in (
        (sync, "hermes_home"),
        (sync, "hermes_config_path"),
        (sync, "hermes_skills_iris_control_dir"),
        (sync, "ensure_hermes_disabled_terminal"),
        (sync, "read_hermes_disabled_toolsets"),
        (sync, "verify_hermes_terminal_disabled"),
        (sync, "ensure_hermes_api_server_computer_use"),
        (sync, "read_hermes_api_server_toolsets"),
        (sync, "verify_hermes_api_server_computer_use"),
        (sync, "ensure_hermes_stdio_dead_check_patch"),
        (sync, "verify_hermes_stdio_dead_check"),
        (ghext, "hermes_home"),
    ):
        assert not hasattr(mod, banned), f"{mod.__name__} still exports {banned}"

    for name in (
        "ensure_iris_agent_disabled_terminal",
        "read_iris_agent_disabled_toolsets",
        "verify_iris_agent_terminal_disabled",
        "ensure_iris_agent_api_server_computer_use",
        "read_iris_agent_api_server_toolsets",
        "verify_iris_agent_api_server_computer_use",
        "ensure_iris_agent_stdio_dead_check_patch",
        "verify_iris_agent_stdio_dead_check",
    ):
        assert callable(getattr(sync, name)), f"missing ControlSync API {name}"

    from iris.infrastructure.agent_runtime import iris_agent_checkout_dir

    assert callable(iris_agent_checkout_dir)

    from iris.infrastructure.iris_agent_credentials import (
        iris_agent_home as creds_home,
        load_iris_agent_dotenv,
        resolve_agent_api_key,
        is_weak_iris_agent_api_key,
    )
    from iris.infrastructure.agent_runtime import iris_agent_home as runtime_home
    from iris.infrastructure.external_api_keys import apply_iris_agent_search_backend
    from iris.storage.iris_agent_login_warm_prefs import (
        load_iris_agent_login_warm,
        save_iris_agent_login_warm,
    )
    from iris.ui.settings.settings_service import load_iris_agent_sync_status_text
    from iris.system.iris_agent_gateway import iris_agent_runtime_report
    from iris.system.iris_agent_install import (
        iris_agent_install_lock,
        iris_agent_python_range,
    )
    assert callable(resolve_agent_api_key)
    params = list(inspect.signature(resolve_agent_api_key).parameters)
    assert params == ["api_key"], params
    assert callable(creds_home) and callable(runtime_home)
    assert callable(load_iris_agent_dotenv)
    assert callable(is_weak_iris_agent_api_key)
    assert callable(apply_iris_agent_search_backend)
    assert callable(load_iris_agent_login_warm)
    assert callable(save_iris_agent_login_warm)
    assert callable(load_iris_agent_sync_status_text)
    skill_src = (_ROOT / "iris/ui/chat/skill_mcp_dialogs.py").read_text(encoding="utf-8")
    assert "def iris_agent_root" in skill_src
    assert "def hermes_root" not in skill_src
    assert callable(iris_agent_runtime_report)
    assert callable(iris_agent_install_lock)
    assert callable(iris_agent_python_range)

    from iris.system import iris_agent_gateway as gw

    for name in (
        "is_iris_agent_gateway_running",
        "is_iris_agent_trampoline_failure",
        "is_iris_agent_cli_missing_failure",
        "is_iris_agent_gateway_dep_missing_failure",
        "ensure_iris_agent_gateway_running",
        "restart_iris_agent_gateway",
        "start_iris_agent_gateway",
        "stop_iris_agent_gateway",
    ):
        assert callable(getattr(gw, name)), f"missing GatewayAPI {name}"
    for banned in (
        "is_hermes_gateway_running",
        "is_hermes_trampoline_failure",
        "is_hermes_cli_missing_failure",
        "is_hermes_gateway_dep_missing_failure",
        "ensure_hermes_gateway_running",
        "restart_hermes_gateway",
        "start_hermes_gateway",
        "stop_hermes_gateway",
    ):
        assert not hasattr(gw, banned), f"gateway still exports {banned}"

    from iris.infrastructure import iris_agent_client as client

    assert callable(client.is_iris_agent_syncable_model)
    assert not hasattr(client, "is_hermes_syncable_model")

    panel_src = (_ROOT / "iris/ui/chat/chat_panel.py").read_text(encoding="utf-8")
    assert "def append_iris_agent_update_prompt" in panel_src
    assert "def dismiss_iris_agent_update_prompt" in panel_src
    assert "iris_agent_update_action_clicked" in panel_src
    assert "append_hermes_update_prompt" not in panel_src
    assert "hermes_update_action_clicked" not in panel_src
    assert "iris-agent-update://" in panel_src
    assert "iris-hermes-update://" not in panel_src

    import iris.infrastructure.iris_agent_credentials as creds

    assert not hasattr(creds, "hermes_home"), "hermes_home alias must be deleted"
    assert not hasattr(creds, "resolve_hermes_api_key")
    assert not hasattr(creds, "load_hermes_dotenv")


def check_no_product_hermes_settings_refs() -> None:
    """Product code must not read Settings.hermes_* or pass hermes_* kwargs."""
    hits: list[str] = []
    for path in _product_py_files():
        rel = path.relative_to(_ROOT).as_posix()
        if rel in _SCRAPE_ALLOWLIST:
            continue
        if _is_thin_hermes_shim(rel):
            continue
        if _is_self_check(rel):
            continue
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if _HERMES_ATTR.search(line) or _HERMES_KWARG.search(line):
                hits.append(f"{rel}:{i}: {line.strip()}")
            elif _RESOLVE_OLD.search(line):
                # Alias assignment in credentials is allowlisted; elsewhere migrate.
                hits.append(f"{rel}:{i}: {line.strip()}")
            elif _LEGACY_ONLINE.search(line) or _LEGACY_ONLINE_KW.search(line):
                hits.append(f"{rel}:{i}: {line.strip()}")
            elif _LEGACY_STATE_KEY.search(line) and "settings.set" not in line:
                # get_state must not emit hermes_*; leftover string mentions in comments/fixtures ok to skip.
                if "hermes_api_key" in line or "hermes_command" in line or "hermes_base_url" in line:
                    continue
                if '"hermes_online"' in line or "'hermes_online'" in line:
                    hits.append(f"{rel}:{i}: {line.strip()}")
    assert not hits, "product still references hermes_* settings/kwargs:\n" + "\n".join(
        hits[:80]
    ) + (f"\n... +{len(hits) - 80} more" if len(hits) > 80 else "")


def check_control_state_agent_online() -> None:
    """Control get_state emits agent_online (not hermes_online)."""
    session = (_ROOT / "iris/ui/control_actions/session.py").read_text(encoding="utf-8")
    assert '"agent_online"' in session, "get_state must emit agent_online"
    assert '"hermes_online"' not in session, "get_state must not emit hermes_online"
    assert "_agent_online" in session
    assert "_use_agent_backend" in (
        _ROOT / "iris/ui/window/main_window.py"
    ).read_text(encoding="utf-8")
    mw = (_ROOT / "iris/ui/window/main_window.py").read_text(encoding="utf-8")
    assert "def _use_agent_backend" in mw
    assert "def _use_hermes_backend" not in mw
    assert "self._agent_online" in mw
    assert "self._hermes_online" not in mw


def check_settings_aliases_gone() -> None:
    from iris.config.settings import Settings

    for name in (
        "hermes_enabled",
        "hermes_command",
        "hermes_base_url",
        "hermes_api_key",
    ):
        assert not hasattr(Settings, name), f"Settings.{name} alias must be deleted"


def main() -> None:
    check_new_names_exist()
    check_forbidden_defs_gone()
    check_settings_aliases_gone()
    check_no_product_hermes_settings_refs()
    check_control_state_agent_online()
    print("agent_product_api_names ok")


if __name__ == "__main__":
    main()
