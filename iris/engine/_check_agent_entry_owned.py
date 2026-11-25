"""ACO-P3: agent_entry exposes AIAgent without binding product to Hermes internals."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def check_agent_entry_source() -> None:
    path = _repo_root() / "iris" / "engine" / "agent_entry.py"
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    froms = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom) and n.module == "run_agent"
    ]
    assert froms, "agent_entry must ImportFrom run_agent"
    names = [a.name for n in froms for a in (n.names or [])]
    assert "AIAgent" in names
    assert "__all__" in src and "AIAgent" in src


def check_sidecar_uses_entry_or_env() -> None:
    from iris.engine import _sidecar_main as sidecar

    src = inspect.getsource(sidecar._import_agent_class)
    assert "IRIS_ENGINE_AGENT_MODULE" in src
    assert "_load_local_helper" in src or "agent_entry" in src


def check_vendor_core_has_run_agent() -> None:
    root = _repo_root() / "vendor" / "iris-agent-core"
    assert (root / "run_agent.py").is_file(), root
    assert (root / "PROVENANCE.md").is_file()
    assert (root / "LICENSE").is_file()
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "iris-agent-core"' in pyproject
    assert (root / "iris_agent_cli").is_dir() or (root / "hermes_cli").is_dir()


if __name__ == "__main__":
    check_vendor_core_has_run_agent()
    check_agent_entry_source()
    check_sidecar_uses_entry_or_env()
    print("agent_entry owned boundary ok")
