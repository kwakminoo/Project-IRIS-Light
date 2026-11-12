"""Unit 0/7 — Freeze C vs B inventory (Iris↔Hermes unification).

Fails when new *logic* ``hermes_*`` product modules appear, or when
``ExternalGateway`` / legacy hermes-home product residue grows outside the
grandfathered allowlist.

Unit 7: thin ``hermes_*`` re-export shims that only forward to ``iris_agent_*``
are **not** counted as product hermes modules (``is_thin_hermes_reexport_shim``).
Logic lives under ``iris_agent_*`` names; the hermes_* allowlist must stay empty
or shrink, never grow.

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_iris_agent_inventory_freeze
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IRIS = ROOT / "iris"

# Unit 7 emptied logic hermes_* product modules (shims excluded from count).
GRANDFATHERED_HERMES_PRODUCT_MODULES: frozenset[str] = frozenset()

# Unit 2 emptied ExternalGateway from the product path.
GRANDFATHERED_EXTERNAL_GATEWAY_PRODUCT_FILES: frozenset[str] = frozenset()

# Unit 3 emptied legacy LOCALAPPDATA hermes home from product error/UI paths.
GRANDFATHERED_LEGACY_HERMES_HOME_PRODUCT_FILES: frozenset[str] = frozenset()

_EXTERNAL_NAME = re.compile(r"\bExternalGateway\b")
_BS = chr(92)
_LEGACY_NEEDLES = (
    "%LOCALAPPDATA%" + _BS + "hermes",
    "%LOCALAPPDATA%" + _BS + _BS + "hermes",
    "%LOCALAPPDATA%/hermes",
)


def _posix(rel: Path) -> str:
    return rel.as_posix()


def _iter_product_py() -> list[Path]:
    out: list[Path] = []
    for path in IRIS.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if path.name.startswith("_check_"):
            continue
        out.append(path)
    return out


def is_thin_hermes_reexport_shim(path: Path) -> bool:
    """True when hermes_*.py only re-exports an iris_agent_* module.

    Allowed: module docstring, ``from __future__``, comments, blank lines,
    and import statements whose module path contains ``iris_agent_``
    (``import *`` or named imports). No other statements (defs, assigns, …).
    """
    if not path.name.startswith("hermes_") or path.suffix != ".py":
        return False
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return False
    saw_iris_agent_import = False
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            # module docstring
            continue
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "__future__":
                continue
            if "iris_agent_" not in mod:
                return False
            saw_iris_agent_import = True
            continue
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "iris_agent_" not in alias.name:
                    return False
                saw_iris_agent_import = True
            continue
        return False
    return saw_iris_agent_import


def discovered_hermes_product_modules() -> set[str]:
    """Logic hermes_* modules only; thin iris_agent_* re-export shims excluded."""
    found: set[str] = set()
    for path in _iter_product_py():
        if not (path.name.startswith("hermes_") and path.suffix == ".py"):
            continue
        if is_thin_hermes_reexport_shim(path):
            continue
        found.add(_posix(path.relative_to(ROOT)))
    return found


def discovered_hermes_shim_modules() -> set[str]:
    found: set[str] = set()
    for path in _iter_product_py():
        if path.name.startswith("hermes_") and is_thin_hermes_reexport_shim(path):
            found.add(_posix(path.relative_to(ROOT)))
    return found


def discovered_external_gateway_product_files() -> set[str]:
    found: set[str] = set()
    for path in _iter_product_py():
        text = path.read_text(encoding="utf-8")
        if _EXTERNAL_NAME.search(text):
            found.add(_posix(path.relative_to(ROOT)))
    return found


def discovered_legacy_hermes_home_product_files() -> set[str]:
    found: set[str] = set()
    for path in _iter_product_py():
        text = path.read_text(encoding="utf-8")
        if any(n in text for n in _LEGACY_NEEDLES):
            found.add(_posix(path.relative_to(ROOT)))
    return found


def _diff(label: str, found: set[str], allowed: frozenset[str]) -> list[str]:
    extra = sorted(found - set(allowed))
    missing = sorted(set(allowed) - found)
    msgs: list[str] = []
    if extra:
        msgs.append(f"{label} grew beyond allowlist:\n  " + "\n  ".join(extra))
    if missing:
        msgs.append(
            f"{label} allowlist stale (path gone; shrink allowlist in later unit):\n  "
            + "\n  ".join(missing)
        )
    return msgs


def main() -> None:
    hits: list[str] = []
    logic = discovered_hermes_product_modules()
    shims = discovered_hermes_shim_modules()
    hits.extend(
        _diff(
            "public hermes_* product modules (logic; shims excluded)",
            logic,
            GRANDFATHERED_HERMES_PRODUCT_MODULES,
        )
    )
    hits.extend(
        _diff(
            "ExternalGateway product files",
            discovered_external_gateway_product_files(),
            GRANDFATHERED_EXTERNAL_GATEWAY_PRODUCT_FILES,
        )
    )
    hits.extend(
        _diff(
            "legacy hermes-home product files",
            discovered_legacy_hermes_home_product_files(),
            GRANDFATHERED_LEGACY_HERMES_HOME_PRODUCT_FILES,
        )
    )
    assert not hits, "inventory freeze failed:\n" + "\n".join(hits)
    print(
        "iris_agent_inventory_freeze ok",
        f"hermes_modules={len(logic)}",
        f"hermes_shims={len(shims)}",
        f"external_gateway_files={len(GRANDFATHERED_EXTERNAL_GATEWAY_PRODUCT_FILES)}",
        f"legacy_home_files={len(GRANDFATHERED_LEGACY_HERMES_HOME_PRODUCT_FILES)}",
    )


if __name__ == "__main__":
    main()
