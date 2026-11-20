"""CLOSED policy — Hermes file/terminal/web/code (+ rest) = REPLACE (not MERGE).

Product decision is permanent: sidecar keeps disabled_toolsets covering Hermes
file/terminal/web/code_execution/memory/delegation/clarify/browser*/computer_use/
tts/vision, then installs Iris familiars / model_tool_names. Do not re-enable
those Hermes toolsets. Do not "merge" Hermes handlers with Iris names.

Scrapes _sidecar_main: construct with the expanded disabled_toolsets, then
_install_iris_engine_tools so Iris Speak + familiar names remain. Not
disable-only: write_file/terminal/web_*/execute_code must be Iris-owned.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from iris.engine.model_tool_names import (
    IRIS_MODEL_TOOLSET,
    iris_backed_model_names,
    iris_model_registrations,
)

_SIDECAR = Path(__file__).resolve().with_name("_sidecar_main.py")

_REQUIRED_DISABLED = frozenset(
    {
        "file",
        "terminal",
        "web",
        "code_execution",
        "memory",
        "delegation",
        "clarify",
        "browser",
        "browser-use",
        "browser-cdp",
        "computer_use",
        "tts",
        "vision",
    }
)


def _disabled_toolsets_literals(tree: ast.AST) -> list[list[str]]:
    found: list[list[str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if not isinstance(key, ast.Constant) or key.value != "disabled_toolsets":
                continue
            if not isinstance(value, (ast.List, ast.Tuple)):
                continue
            items: list[str] = []
            for elt in value.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    items.append(elt.value)
            found.append(items)
    return found


def _order_ok(src: str) -> bool:
    marker = "wanted = {"
    i_wanted = src.find(marker)
    if i_wanted < 0:
        return False
    block = src[i_wanted:]
    i_disabled = block.find('"disabled_toolsets"')
    i_install = block.find("_install_iris_engine_tools(")
    if i_disabled < 0 or i_install < 0:
        return False
    return i_disabled < i_install


def _check_model_names_iris_install(src: str) -> None:
    """Product path installs Iris-backed model names (not empty disable-only)."""
    assert "model_tool_names" in src, "_sidecar_main must load model_tool_names"
    assert "_load_local_helper" in src and '_load_local_helper("model_tool_names")' in src, (
        "sidecar must file-location-load model_tool_names (no iris.engine package import)"
    )
    assert "from iris.engine.model_tool_names" not in src, (
        "package import of model_tool_names pulls PyQt6 via iris.engine.__init__"
    )
    assert "iris_model_registrations" in src, (
        "sidecar must call iris_model_registrations for catalog replace"
    )
    assert "as_model_surface" in src, "sidecar must normalize speak_surface for Control"
    assert "adapt_control_invoke" in src, (
        "sidecar must adapt model args → Control invoke args"
    )
    assert "override=True" in src, (
        "model register must override=True so Hermes file/terminal handlers are replaced"
    )
    assert (
        f'toolset={IRIS_MODEL_TOOLSET!r}' in src
        or f'toolset="{IRIS_MODEL_TOOLSET}"' in src
        or "IRIS_MODEL_TOOLSET" in src
    ), f"model register must use Iris ownership marker {IRIS_MODEL_TOOLSET!r}"

    home_regs = iris_model_registrations("home")
    names = {row[0] for row in home_regs}
    expected = set(iris_backed_model_names())
    assert names == expected, f"iris_model_registrations home={names} expected={expected}"
    assert "write_file" in names and "terminal" in names
    assert "web_search" in names and "web_extract" in names
    assert "execute_code" in names
    for name, action, body in home_regs:
        assert action, f"{name} missing control action"
        assert "description" in body and "parameters" in body

    # Hermes upstream toolsets stay disabled; model names must not re-enable them.
    assert not re.search(
        r'disabled_toolsets["\']?\s*:\s*\[\s*\]', src
    ), "disabled_toolsets must not be emptied"


def main() -> None:
    src = _SIDECAR.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(_SIDECAR))
    literals = _disabled_toolsets_literals(tree)
    assert literals, "sidecar must pass disabled_toolsets to AIAgent"
    flat = {name for row in literals for name in row}
    missing = sorted(_REQUIRED_DISABLED - flat)
    assert not missing, f"disabled_toolsets missing {missing}: {literals}"
    assert _order_ok(src), (
        "disabled_toolsets must be set on AIAgent before _install_iris_engine_tools"
    )
    assert re.search(
        r"disabled_toolsets", src
    ), "disabled_toolsets marker missing from _sidecar_main"
    _check_model_names_iris_install(src)
    print(
        "sidecar_disables_agent_file_terminal ok",
        "status=CLOSED",
        "policy=REPLACE",
        f"disabled_toolsets={literals[0]}",
        f"iris_model_names={iris_backed_model_names()}",
        f"ownership={IRIS_MODEL_TOOLSET}",
    )


if __name__ == "__main__":
    main()
