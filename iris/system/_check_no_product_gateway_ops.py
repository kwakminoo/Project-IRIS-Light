"""PR-A / Unit 2 Delete — product ops must not start/restart :8642 gateway.

Chat uses InternalSidecar. Product sync is skills/config scrub + SpeakTools only.

Scrape (non-_check) product paths for lifecycle ensure/restart/start
(iris_agent_* and any leftover hermes_* names). Assert zero callers.
Lifecycle APIs are gutted stubs (no _popen_hidden).
Also assert product sync never passes reconnect_gateway=True.

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_no_product_gateway_ops
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]

_FORBIDDEN = frozenset(
    {
        "restart_iris_agent_gateway",
        "ensure_iris_agent_gateway_running",
        "start_iris_agent_gateway",
        # leftover names must stay forbidden if any caller reappears
        "restart_agent_gateway",
        "ensure_agent_gateway_running",
        "start_agent_gateway",
    }
)

# Product surfaces that must not touch :8642 lifecycle.
# iris/system/*.py covers update/install/control; gateway module itself is exempt.
_PRODUCT_GLOBS = (
    "iris/ui/workers/*.py",
    "iris/ui/control_actions/*.py",
    "iris/infrastructure/agent_runtime.py",
    "iris/system/*.py",
)

_SYSTEM_EXEMPT = frozenset({"iris_agent_gateway.py"})

_RECONNECT_TRUE = re.compile(r"reconnect_gateway\s*=\s*True")


def _product_files() -> list[Path]:
    seen: set[Path] = set()
    out: list[Path] = []
    for pattern in _PRODUCT_GLOBS:
        for path in sorted(_ROOT.glob(pattern)):
            if not path.is_file():
                continue
            name = path.name
            if name.startswith("_check_") or name.startswith("test_"):
                continue
            if name in _SYSTEM_EXEMPT:
                continue
            if path in seen:
                continue
            seen.add(path)
            out.append(path)
    return out


def _forbidden_names_in_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(text, filename=str(path))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN:
            hits.append(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN:
            hits.append(node.attr)
        elif isinstance(node, ast.alias) and node.name in _FORBIDDEN:
            hits.append(node.name)
        elif isinstance(node, ast.alias) and node.asname in _FORBIDDEN:
            hits.append(node.asname)
    return sorted(set(hits))


def _check_no_forbidden_gateway_ops() -> None:
    offenders: list[str] = []
    for path in _product_files():
        hits = _forbidden_names_in_file(path)
        if hits:
            rel = path.relative_to(_ROOT).as_posix()
            offenders.append(f"{rel}: {', '.join(hits)}")
    assert not offenders, (
        "product paths must not call :8642 gateway ops:\n  "
        + "\n  ".join(offenders)
    )


def _check_product_sync_never_reconnects_gateway() -> None:
    """UI/workers + control_actions + sync module product entry never pass True."""
    offenders: list[str] = []
    for path in _product_files():
        text = path.read_text(encoding="utf-8-sig")
        if path.name == "iris_agent_control_sync.py":
            # Parameter default / docs OK; only call sites with True are banned.
            tree = ast.parse(text, filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = ""
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if name != "sync_iris_control":
                    continue
                for kw in node.keywords:
                    if kw.arg == "reconnect_gateway" and isinstance(
                        kw.value, ast.Constant
                    ):
                        if kw.value.value is True:
                            offenders.append(
                                f"{path.relative_to(_ROOT).as_posix()}:"
                                f"{node.lineno} reconnect_gateway=True"
                            )
            continue
        if _RECONNECT_TRUE.search(text):
            offenders.append(path.relative_to(_ROOT).as_posix())
    assert not offenders, (
        "product sync must use reconnect_gateway=False (or omit):\n  "
        + "\n  ".join(offenders)
    )


def _check_sync_default_is_false() -> None:
    from iris.system.iris_agent_control_sync import sync_iris_control

    params = inspect.signature(sync_iris_control).parameters
    assert params["reconnect_gateway"].default is False


def _check_lifecycle_apis_gutted() -> None:
    """Unit 2 Delete: start/ensure/restart/prune must not spawn :8642."""
    from iris.system import iris_agent_gateway as gw

    for name in (
        "start_iris_agent_gateway",
        "ensure_iris_agent_gateway_running",
        "restart_iris_agent_gateway",
    ):
        src = inspect.getsource(getattr(gw, name))
        assert "_popen_hidden" not in src, f"{name} must not spawn"
        assert "gateway run" not in src.lower() or "Unit 2 Delete" in src
    assert gw.start_iris_agent_gateway() is False
    assert gw.ensure_iris_agent_gateway_running("http://127.0.0.1:8642/v1") is False
    assert gw.restart_iris_agent_gateway("http://127.0.0.1:8642/v1") is False
    assert gw.prune_orphan_gateway_procs("http://127.0.0.1:8642/v1") == 0
    assert gw.is_iris_agent_gateway_running("") is False
    assert gw.probe_gateway_health("").ok is False
    for banned in (
        "start_agent_gateway",
        "ensure_agent_gateway_running",
        "restart_agent_gateway",
        "is_agent_gateway_running",
    ):
        assert not hasattr(gw, banned), f"legacy {banned} must be deleted"


def main() -> None:
    _check_sync_default_is_false()
    _check_no_forbidden_gateway_ops()
    _check_product_sync_never_reconnects_gateway()
    _check_lifecycle_apis_gutted()
    print("no_product_gateway_ops ok")


if __name__ == "__main__":
    main()
