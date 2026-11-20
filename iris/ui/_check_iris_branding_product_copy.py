"""Product-path string literals must not present Hermes as the Iris brand.

Scans selected non-UI product modules (API key blurbs, setup logos).
NOTICE/LICENSE and vendor package paths are out of scope.

Run:
  .venv\\Scripts\\python.exe -m iris.ui._check_iris_branding_product_copy
"""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_TARGETS = (
    _ROOT / "iris" / "infrastructure" / "external_api_keys.py",
    _ROOT / "iris" / "assets" / "setup_logos.py",
    _ROOT / "iris" / "browser" / "observation.py",
)

_FORBIDDEN_SUBSTRINGS = (
    "Hermes 웹검색",
    "Hermes를",
    "Hermes 를",
    "Hermes가",
    "Hermes 가",
    "Do not use Hermes",
    '"Hermes"',
    "'Hermes'",
)


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
            for v in node.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    out.append((getattr(node, "lineno", 0), v.value))
    return out


def find_forbidden_product_copy() -> list[str]:
    hits: list[str] = []
    for path in _TARGETS:
        if not path.is_file():
            hits.append(f"missing:{path.relative_to(_ROOT)}")
            continue
        rel = path.relative_to(_ROOT)
        for lineno, text in _string_literals(path):
            for needle in _FORBIDDEN_SUBSTRINGS:
                # Exact brand label check for setup_logos: value == Hermes
                if needle in ('"Hermes"', "'Hermes'"):
                    if text == "Hermes":
                        hits.append(f"{rel}:{lineno}: brand label {text!r}")
                    continue
                if needle in text:
                    hits.append(f"{rel}:{lineno}: contains {needle!r} in {text[:80]!r}")
    return hits


def main() -> int:
    hits = find_forbidden_product_copy()
    if hits:
        print("iris_branding_product_copy FAIL")
        for h in hits:
            print(h)
        return 1
    print("iris_branding_product_copy ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
