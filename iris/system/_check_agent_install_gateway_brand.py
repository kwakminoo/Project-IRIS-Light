"""Gateway / setup / install user+log brand — Iris Agent, not bare Hermes.

Scrape rule (AST only, docstring lines skipped):
  string literals that appear in
    - ``return`` values (Constant / JoinedStr parts)
    - call kwargs named ``message``
    - call args to ``on_progress``, ``_emit``, ``_emit_stream``, ``_progress``, ``print``
  inside:
    iris/system/iris_agent_gateway.py
    iris/system/setup_protocol.py
    iris/system/iris_agent_install.py

Fails when a scraped literal still has product voice:
  - bare ``Hermes`` / ``헤르메스``
  - phrase ``hermes 실행``
  - bare ``hermes_cli 없음`` / ``hermes_cli import`` without Iris Agent wording

Allows: URL hosts, filesystem candidates (hermes-agent.exe / hermes.exe),
``import hermes_cli`` probe snippets, and ``hermes_cli`` when paired with
``Iris Agent`` / ``iris-agent CLI``.

Also asserts ``IRIS_AGENT_INSTALL_URL`` exists and product NeedsUser paths
prefer that name (``HERMES_INSTALL_URL`` may remain as a thin alias).

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_agent_install_gateway_brand
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_TARGETS = (
    _ROOT / "iris" / "system" / "iris_agent_gateway.py",
    _ROOT / "iris" / "system" / "setup_protocol.py",
    _ROOT / "iris" / "system" / "iris_agent_install.py",
)

_EMIT_FUNCS = frozenset(
    {"on_progress", "_emit", "_emit_stream", "_progress", "print"}
)

_BRAND = re.compile(r"(?<![A-Za-z_])Hermes(?![A-Za-z_])|헤르메스")
_HERMES_RUN = re.compile(r"hermes 실행", re.IGNORECASE)
_BARE_CLI = re.compile(r"(?<![A-Za-z_(])hermes_cli (없음|import)")

_ALLOW_SUBSTR = (
    "hermes-agent.nousresearch.com",
    "hermes-agent.exe",
    "hermes.exe",
    "hermes.cmd",
    "import hermes_cli",
    "hermes_cli.main",
    "No module named 'hermes_cli'",
    'No module named "hermes_cli"',
    "file:///tmp/hermes-agent",
    "platform\": \"hermes-agent",
    "platform': 'hermes-agent",
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
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            _mark(node)
    return lines


def _parts(node: ast.AST) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        out.append((getattr(node, "lineno", 0), node.value))
    elif isinstance(node, ast.JoinedStr):
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                out.append((getattr(v, "lineno", 0), v.value))
    elif isinstance(node, (ast.Tuple, ast.List)):
        for elt in node.elts:
            out.extend(_parts(elt))
    elif isinstance(node, ast.BinOp):
        out.extend(_parts(node.left))
        out.extend(_parts(node.right))
    elif isinstance(node, ast.Call):
        for a in node.args:
            out.extend(_parts(a))
        for kw in node.keywords:
            out.extend(_parts(kw.value))
    return out


def _call_name(node: ast.Call) -> str:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def _scraped_literals(path: Path) -> list[tuple[int, str]]:
    src = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(src, filename=str(path))
    docs = _docstring_lines(tree)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Return) and node.value is not None:
            found.extend(_parts(node.value))
        elif isinstance(node, ast.Call):
            name = _call_name(node)
            if name in _EMIT_FUNCS:
                for a in node.args:
                    found.extend(_parts(a))
                for kw in node.keywords:
                    found.extend(_parts(kw.value))
            for kw in node.keywords:
                if kw.arg == "message":
                    found.extend(_parts(kw.value))
    # Dedup + skip docstring lines
    seen: set[tuple[int, str]] = set()
    out: list[tuple[int, str]] = []
    for lineno, text in found:
        if lineno in docs:
            continue
        key = (lineno, text)
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _scrub_allows(s: str) -> str:
    scrub = s
    for token in _ALLOW_SUBSTR:
        scrub = scrub.replace(token, "")
    return scrub


def _has_iris_cli_pairing(s: str) -> bool:
    return "Iris Agent" in s or "iris-agent CLI" in s or "iris-agent" in s.lower()


def _is_bad(s: str) -> bool:
    scrub = _scrub_allows(s)
    if _BRAND.search(scrub):
        return True
    if _HERMES_RUN.search(scrub):
        return True
    if _BARE_CLI.search(scrub) and not _has_iris_cli_pairing(s):
        return True
    return False


def find_brand_hits() -> list[str]:
    hits: list[str] = []
    for path in _TARGETS:
        if not path.is_file():
            hits.append(f"missing:{path.relative_to(_ROOT)}")
            continue
        for lineno, text in _scraped_literals(path):
            if _is_bad(text):
                rel = path.relative_to(_ROOT)
                hits.append(f"{rel}:{lineno}: {text[:140]!r}")
    return hits


def _assert_install_url_alias() -> None:
    setup = _ROOT / "iris" / "system" / "setup_protocol.py"
    src = setup.read_text(encoding="utf-8", errors="replace")
    assert re.search(
        r"^IRIS_AGENT_INSTALL_URL\s*=", src, re.MULTILINE
    ), "prefer IRIS_AGENT_INSTALL_URL name"
    assert "HERMES_INSTALL_URL = IRIS_AGENT_INSTALL_URL" in src, (
        "HERMES_INSTALL_URL must stay a thin alias"
    )
    product_uses = src.count("action_url=IRIS_AGENT_INSTALL_URL") + src.count(
        "IRIS_AGENT_INSTALL_URL,"
    )
    assert product_uses >= 1, "NeedsUser/install paths should use IRIS_AGENT_INSTALL_URL"
    assert "+ IRIS_AGENT_INSTALL_URL" in src, (
        "official installer should irm IRIS_AGENT_INSTALL_URL"
    )
    # Product copy must not advertise bare Hermes around the docs link.
    assert "Iris Agent를 수동으로 설치" in src or "Iris Agent 런타임 설치" in src


def main() -> int:
    hits = find_brand_hits()
    if hits:
        print("agent_install_gateway_brand FAIL")
        for h in hits:
            print(h)
        return 1
    _assert_install_url_alias()
    print("agent_install_gateway_brand ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
