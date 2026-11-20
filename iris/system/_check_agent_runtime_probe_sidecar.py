"""Product setup probe = InternalSidecar import readiness (not :8642).

Asserts:
  - probe_agent_runtime exists; probe_agent_runtime gone
  - product setup never calls ensure/restart/start_*gateway
  - probe failure strings used for repair are sidecar-relevant
  - probe import set has no aiohttp (gateway remnant)

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_agent_runtime_probe_sidecar
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from iris.system import iris_agent_gateway as gw
from iris.system.setup_protocol import SetupProtocol

_ROOT = Path(__file__).resolve().parents[2]
_FORBIDDEN_GATEWAY_OPS = frozenset(
    {
        "restart_iris_agent_gateway",
        "ensure_iris_agent_gateway_running",
        "start_iris_agent_gateway",
    }
)
_PRODUCT_SCRAPE = (
    _ROOT / "iris" / "system" / "setup_protocol.py",
    _ROOT / "iris" / "system" / "iris_agent_install.py",
    _ROOT / "iris" / "ui" / "_check_setup_agent_live.py",
)


def _check_probe_name_migrated() -> None:
    assert hasattr(gw, "probe_agent_runtime")
    assert not hasattr(gw, "probe_agent_runtime"), (
        "probe_agent_runtime must be deleted (no alias)"
    )
    src = inspect.getsource(gw.probe_agent_runtime)
    assert "aiohttp" not in src, "product probe must drop aiohttp"
    assert "from run_agent import AIAgent" in src
    assert "import hermes_cli" in src
    assert "sidecar 의존성" in src
    assert "gateway 의존성 없음" not in src


def _names_in_tree(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
        elif isinstance(node, ast.alias):
            out.add(node.name)
            if node.asname:
                out.add(node.asname)
    return out


def _check_product_no_gateway_lifecycle() -> None:
    offenders: list[str] = []
    for path in _PRODUCT_SCRAPE:
        if not path.is_file():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        names = _names_in_tree(tree)
        hits = sorted(names & _FORBIDDEN_GATEWAY_OPS)
        if hits:
            offenders.append(f"{path.relative_to(_ROOT).as_posix()}: {', '.join(hits)}")
        text = path.read_text(encoding="utf-8-sig")
        assert "probe_agent_runtime" not in text, path
        assert "probe_agent_runtime" in text or path.name.endswith(
            "_check_setup_agent_live.py"
        )
    assert not offenders, "product setup must not call :8642 ops:\n" + "\n".join(
        offenders
    )


def _check_setup_step_uses_sidecar_probe() -> None:
    src = Path(_ROOT / "iris" / "system" / "setup_protocol.py").read_text(
        encoding="utf-8-sig"
    )
    assert "probe_agent_runtime" in src
    assert "probe_agent_runtime" not in src
    # Auto-repair still keys off sidecar-relevant failure strings.
    assert "sidecar 의존성" in src
    assert "start_gateway=False" in src
    assert "Iris Agent sidecar ready" in src


def _check_failure_helpers_still_repair() -> None:
    assert gw.is_iris_agent_cli_missing_failure(
        "ModuleNotFoundError: No module named 'hermes_cli'"
    )
    assert gw.is_iris_agent_gateway_dep_missing_failure(
        "ModuleNotFoundError: No module named 'mcp'"
    )
    assert gw.is_iris_agent_gateway_dep_missing_failure(
        "ModuleNotFoundError: No module named 'run_agent'"
    )
    assert gw.is_iris_agent_trampoline_failure(
        "error: Failed to spawn: uv trampoline failed\n"
        "Caused by: entity not found (os error 2)"
    )


def _check_step_source_ast() -> None:
    tree = ast.parse(
        (_ROOT / "iris" / "system" / "setup_protocol.py").read_text(
            encoding="utf-8-sig"
        )
    )
    step = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_step_agent_runtime":
            step = node
            break
    assert step is not None
    names = _names_in_tree(step)
    assert "probe_agent_runtime" in names
    assert not (names & _FORBIDDEN_GATEWAY_OPS)
    # Ensure dry path symbol exists for importers.
    assert callable(SetupProtocol()._step_agent_runtime)


def _main() -> None:
    _check_probe_name_migrated()
    _check_product_no_gateway_lifecycle()
    _check_setup_step_uses_sidecar_probe()
    _check_failure_helpers_still_repair()
    _check_step_source_ast()
    print("agent_runtime_probe_sidecar check ok")


if __name__ == "__main__":
    _main()
