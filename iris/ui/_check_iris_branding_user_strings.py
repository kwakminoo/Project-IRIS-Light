"""User-visible Hermes branding must not appear in Iris UI product strings.

NOTICE/LICENSE and third-party notices are out of scope.
Worker class names are covered by _check_iris_branding_worker_aliases.

Run:
  .venv\\Scripts\\python.exe -m iris.ui._check_iris_branding_user_strings
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_UI_ROOT = Path(__file__).resolve().parent
_FORBIDDEN_SUBSTRINGS = (
    "Hermes API",
    "Hermes를",
    "Hermes 를",
    "Hermes가",
    "Hermes 가",
    "Hermes model sync",
    "Ollama/Hermes",
    "Hermes AGENT",
    "Hermes Skills",
    "Hermes/Ollama",
    "Hermes 연결",
    "Hermes terminal",
    "너는 Hermes",
)

# Product UI modules only (skip self-checks and generated).
_SKIP_NAME_PARTS = ("_check_", "__pycache__")


def _ui_py_files() -> list[Path]:
    out: list[Path] = []
    for path in _UI_ROOT.rglob("*.py"):
        name = path.name
        if any(part in name for part in _SKIP_NAME_PARTS):
            continue
        if "__pycache__" in path.parts:
            continue
        out.append(path)
    return out


def _string_literals(path: Path) -> list[tuple[int, str]]:
    src = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        return []
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append((getattr(node, "lineno", 0), node.value))
        elif isinstance(node, ast.JoinedStr):
            # f-string pieces that are plain constants
            for v in node.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    out.append((getattr(node, "lineno", 0), v.value))
    return out


def find_forbidden_user_strings() -> list[str]:
    hits: list[str] = []
    for path in _ui_py_files():
        rel = path.relative_to(_UI_ROOT.parent.parent)
        for lineno, text in _string_literals(path):
            for needle in _FORBIDDEN_SUBSTRINGS:
                if needle in text:
                    hits.append(f"{rel}:{lineno}: contains {needle!r} in {text[:80]!r}")
    return hits


def main() -> int:
    hits = find_forbidden_user_strings()
    if hits:
        print("iris_branding_user_strings FAIL")
        for h in hits:
            print(h)
        return 1
    print("iris_branding_user_strings ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
