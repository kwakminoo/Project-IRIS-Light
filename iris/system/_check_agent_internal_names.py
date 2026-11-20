"""Unit 3 — locked internal product identifiers are agent_*/iris_agent_*, not hermes_*.

Migrate callers and delete old ``def`` names in one wave (no alias shims).

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_agent_internal_names
"""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

# (module relative to repo, forbidden def name, required def name)
_LOCKED = (
    ("iris/ui/workers/backend_call.py", "_hermes", "_agent"),
    ("iris/infrastructure/iris_agent_errors.py", "format_hermes_sse_error", "format_agent_sse_error"),
    ("iris/infrastructure/iris_agent_errors.py", "format_hermes_http_401", "format_agent_http_401"),
    (
        "iris/infrastructure/iris_agent_errors.py",
        "scrub_upstream_hermes_cli_hints",
        "scrub_upstream_cli_hints",
    ),
    ("iris/infrastructure/iris_agent_client.py", "host_label_for_hermes", "host_label_for_agent"),
    (
        "iris/system/iris_agent_control_sync.py",
        "_hermes_mcp_tool_candidates",
        "_agent_mcp_tool_candidates",
    ),
    (
        "iris/system/iris_agent_control_sync.py",
        "_hermes_mcp_tool_path",
        "_agent_mcp_tool_path",
    ),
    (
        "iris/system/iris_agent_install.py",
        "force_retire_hermes_agent",
        "force_retire_iris_agent",
    ),
    (
        "iris/system/iris_agent_install.py",
        "_kill_hermes_tree_holders",
        "_kill_agent_tree_holders",
    ),
    (
        "iris/system/iris_agent_install.py",
        "is_supported_hermes_python",
        "is_supported_agent_python",
    ),
    ("iris/system/iris_agent_gateway.py", "_hermes_agent_dir", "_iris_agent_dir"),
    ("iris/system/iris_agent_gateway.py", "_hermes_venv_dir", "_iris_agent_venv_dir"),
    (
        "iris/system/iris_agent_gateway.py",
        "_hermes_venv_python",
        "_iris_agent_venv_python",
    ),
    (
        "iris/system/iris_agent_gateway.py",
        "_hermes_committed_python",
        "_iris_agent_committed_python",
    ),
    (
        "iris/system/iris_agent_gateway.py",
        "_hermes_module_cmd",
        "_iris_agent_module_cmd",
    ),
    (
        "iris/system/setup_protocol.py",
        "_wipe_hermes_agent_runtime",
        "_wipe_agent_runtime",
    ),
    (
        "iris/system/setup_protocol.py",
        "_run_hermes_official_installer",
        "_run_agent_official_installer",
    ),
    ("iris/system/setup_protocol.py", "_hermes_done", "_agent_done"),
    ("iris/system/setup_protocol.py", "_hermes_cancelled", "_agent_cancelled"),
    ("iris/system/setup_protocol.py", "_hermes_user_fail", "_agent_user_fail"),
    (
        "iris/system/setup_protocol.py",
        "_install_hermes_bypass",
        "_install_agent_bypass",
    ),
    ("iris/system/setup_protocol.py", "_install_hermes", "_install_agent"),
)


def _top_level_and_method_defs(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.add(child.name)
    return names


def check_locked_renames() -> None:
    missing_new: list[str] = []
    leftover_old: list[str] = []
    for rel, old, new in _LOCKED:
        path = _ROOT / rel
        assert path.is_file(), path
        names = _top_level_and_method_defs(path)
        if new not in names:
            missing_new.append(f"{rel}: missing def {new}")
        if old in names:
            leftover_old.append(f"{rel}: still defines {old}")
    assert not leftover_old, "locked old defs remain:\n" + "\n".join(leftover_old)
    assert not missing_new, "locked new defs missing:\n" + "\n".join(missing_new)


def main() -> None:
    check_locked_renames()
    print("agent_internal_names ok")


if __name__ == "__main__":
    main()
