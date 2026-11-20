"""Unit 6 — user-facing / product-default copy must not imply HTTP :8642.

Product chat is InternalSidecar. Opt-in gateway URLs may still appear in
diagnostics modules, tests, fixtures, and gateway infrastructure.

Scrape string literals (docstrings skipped) in product surfaces for ``8642``.
Also assert Settings / load_settings product default has no invented :8642.

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_no_user_facing_8642
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parents[2]

# Product surfaces that must not show :8642 to users / agents as the live path.
_SCAN_GLOBS = (
    "iris/ui/**/*.py",
    "iris/config/settings.py",
    "iris/infrastructure/__init__.py",
    "iris/system/iris_agent_memory_nudge.py",
    "iris/knowledge/iris_state.py",
    "iris/ui/ai_hub/routing_panel.py",
)

# Allow explicit opt-in / fixture markers inside otherwise scanned files.
_ALLOW_SUBSTRINGS = (
    "test fixture",
    "fixture URL",
    "opt-in",
    "Opt-in",
    "self-check",
)


def _docstring_lines(tree: ast.AST) -> set[int]:
    lines: set[int] = set()

    def _mark(node: ast.AST) -> None:
        body = getattr(node, "body", None)
        if not body:
            return
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            lines.add(getattr(first.value, "lineno", 0))

    _mark(tree)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            _mark(node)
    return lines


def _main_block_lines(tree: ast.AST) -> set[int]:
    """Lines under ``if __name__ == '__main__':`` — self-checks / fixtures OK."""
    lines: set[int] = set()
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name)
            and test.left.id == "__name__"
        ):
            continue
        for child in ast.walk(node):
            lineno = getattr(child, "lineno", None)
            if isinstance(lineno, int):
                lines.add(lineno)
    return lines


def _scan_file(path: Path) -> list[str]:
    rel = path.relative_to(_ROOT).as_posix()
    if path.name.startswith("_check_") or path.name.startswith("test_"):
        return []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return []
    docs = _docstring_lines(tree)
    mains = _main_block_lines(tree)
    hits: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        lineno = getattr(node, "lineno", 0)
        if lineno in docs or lineno in mains:
            continue
        s = node.value
        if "8642" not in s:
            continue
        if any(a in s for a in _ALLOW_SUBSTRINGS):
            continue
        hits.append(f"{rel}:{lineno}: {s[:120]!r}")
    return hits


def _product_files() -> list[Path]:
    seen: set[Path] = set()
    out: list[Path] = []
    for pattern in _SCAN_GLOBS:
        for path in sorted(_ROOT.glob(pattern)):
            if not path.is_file():
                continue
            if "__pycache__" in path.parts:
                continue
            if path in seen:
                continue
            seen.add(path)
            out.append(path)
    return out


def check_no_user_facing_8642_literals() -> None:
    offenders: list[str] = []
    for path in _product_files():
        offenders.extend(_scan_file(path))
    assert not offenders, (
        "user-facing product copy must not imply :8642:\n  "
        + "\n  ".join(offenders)
    )


def check_settings_default_empty() -> None:
    from iris.config.settings import Settings, load_settings

    assert Settings().agent_base_url == ""
    keys = (
        "IRIS_AGENT_BASE_URL",
        "IRIS_HERMES_BASE_URL",
    )
    with mock.patch.dict(os.environ, {k: "" for k in keys}, clear=False):
        for k in keys:
            os.environ.pop(k, None)
        s = load_settings(env_path=Path("__no_dotenv_8642_scrape__"))
    assert s.agent_base_url == ""
    assert "8642" not in (s.agent_base_url or "")


def check_env_8642_base_url_force_stripped() -> None:
    """load_settings / env boundary never returns a live :8642 product URL."""
    from iris.config.settings import load_settings

    with mock.patch.dict(
        os.environ,
        {
            "IRIS_AGENT_BASE_URL": "http://127.0.0.1:8642/v1",
            "IRIS_HERMES_BASE_URL": "http://localhost:8642/v1",
        },
        clear=False,
    ):
        s = load_settings(env_path=Path("__no_dotenv_8642_scrape__"))
        assert s.agent_base_url == ""
        assert "8642" not in (s.agent_base_url or "")
        # Load strips for Settings only; does not rewrite os.environ.
        assert ":8642" in (os.environ.get("IRIS_AGENT_BASE_URL") or "")


def check_ide_hero_sidecar_pill() -> None:
    path = _ROOT / "iris" / "ui" / "ide" / "iris_ide_hero_overlay.py"
    text = path.read_text(encoding="utf-8-sig")
    assert '("AGENT", "SIDECAR"' in text or "(\"AGENT\", \"SIDECAR\"" in text
    assert "8642" not in text


def main() -> None:
    check_settings_default_empty()
    check_env_8642_base_url_force_stripped()
    check_ide_hero_sidecar_pill()
    check_no_user_facing_8642_literals()
    print("no_user_facing_8642 ok")


if __name__ == "__main__":
    main()
