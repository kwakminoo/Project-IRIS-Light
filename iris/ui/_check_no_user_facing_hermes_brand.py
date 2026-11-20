"""User/agent-facing product copy must not brand as Hermes.

Scans:
  - iris/ui non-_check_*.py string literals (docstrings skipped)
  - integrations/iris-skills/**/*.md
  - iris/system/iris_agent_memory_nudge.py
  - iris/ui/control_actions (summaries + action_catalog.json)
  - iris/knowledge/iris_state.py + iris_wiki.py agent-facing labels

Allows: hermes_* keys, iris-agent-update://, agent_command path tokens,
backend enum HERMES in tests. Hermes*Worker shims are deleted (not allowed).

Run:
  .venv\\Scripts\\python.exe -m iris.ui._check_no_user_facing_agent_brand
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_UI = _ROOT / "iris" / "ui"
_SKILLS = _ROOT / "integrations" / "iris-skills"

_BRAND = re.compile(r"(?<![A-Za-z_])Hermes(?![A-Za-z_])|헤르메스|(?<![A-Za-z_])HERMES(?![A-Za-z_])")

# Exact / shape allows — identifiers, shims, protocol keys, not product brand.
_ALLOW_EXACT = {
    "hermes",
    "hermes_enabled",
    # Legacy identifier strings (catalog scrub / fixtures); not live Settings fields.
    "hermes_api_key",
    "hermes_command",
    "hermes_base_url",
    "agent_running",
    "agent_exe",
    "hermes_exe",
    "hermes_install",
    "hermes_env",
    "hermes_provider",
    "agent_runtime",
    "iris_agent_update",
    "_agent_login_warm_box",
    "_agent_login_warm_wanted",
    "resolve_hermes_inference",
    "wiki_requests_go_to_hermes()",
    "hermes stream must not run after sync fail + base_url",
    "hermes_update_worker ok",
}

_ALLOW_PREFIX = (
    "iris-agent-update://",
)

_ALLOW_RE = (
    # Identifier keys only (lowercase hermes_*), not brand HERMES / Hermes.
    re.compile(r"^_?hermes(_[a-z0-9]+)*$"),
    re.compile(r"^BACKEND_HERMES$"),
    # Upstream error fixtures used only in decide_fallback asserts.
    re.compile(r"^Hermes HTTP \d+"),
)


def _is_allowed(s: str) -> bool:
    t = s.strip()
    if t in _ALLOW_EXACT:
        return True
    for pref in _ALLOW_PREFIX:
        if t.startswith(pref):
            return True
    for rx in _ALLOW_RE:
        if rx.match(t):
            return True
    # Path / package tokens inside longer strings.
    scrub = t
    for token in (
        "hermes-agent",
        "skills/iris-control",
        "skills/iris-agent",
        "HERMES_HOME",
        "IRIS_HERMES_",
        "X-Hermes-Model",
        "hermes_workers",
        "hermes_cli",
        "NousResearch/hermes",
    ):
        scrub = scrub.replace(token, "")
    return _BRAND.search(scrub) is None and "헤르메스" not in scrub


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


def _ui_literal_hits() -> list[str]:
    hits: list[str] = []
    for path in _UI.rglob("*.py"):
        if path.name.startswith("_check_"):
            continue
        if "__pycache__" in path.parts:
            continue
        src = path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(src, filename=str(path))
        except SyntaxError:
            continue
        docs = _docstring_lines(tree)
        for node in ast.walk(tree):
            vals: list[tuple[int, str]] = []
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                vals.append((getattr(node, "lineno", 0), node.value))
            elif isinstance(node, ast.JoinedStr):
                for v in node.values:
                    if isinstance(v, ast.Constant) and isinstance(v.value, str):
                        vals.append((getattr(node, "lineno", 0), v.value))
            for lineno, text in vals:
                if lineno in docs:
                    continue
                if not _BRAND.search(text) and "헤르메스" not in text:
                    continue
                if _is_allowed(text):
                    continue
                rel = path.relative_to(_ROOT)
                hits.append(f"{rel}:{lineno}: {text[:120]!r}")
    return hits


def _md_hits() -> list[str]:
    hits: list[str] = []
    if not _SKILLS.is_dir():
        return hits
    for path in _SKILLS.rglob("*.md"):
        for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if not _BRAND.search(line) and "헤르메스" not in line:
                continue
            # SpeakTools / path tokens ok; bare Hermes brand is not.
            if _is_allowed(line.strip()):
                continue
            scrub = line
            for token in (
                "hermes-agent",
                "skills/iris-control",
                "skills/iris-agent",
                "HERMES_HOME",
            ):
                scrub = scrub.replace(token, "")
            if _BRAND.search(scrub) or "헤르메스" in scrub:
                rel = path.relative_to(_ROOT)
                hits.append(f"{rel}:{i}: {line.strip()[:120]!r}")
    return hits


def _extra_file_hits() -> list[str]:
    hits: list[str] = []
    extras = (
        _ROOT / "iris" / "system" / "iris_agent_memory_nudge.py",
        _ROOT / "iris" / "system" / "iris_agent_login_warm.py",
        _ROOT / "iris" / "knowledge" / "iris_state.py",
        _ROOT / "iris" / "knowledge" / "iris_wiki.py",
        _ROOT / "iris" / "ui" / "control_actions" / "agent_turn.py",
        _ROOT / "iris" / "ui" / "control_actions" / "action_catalog.json",
    )
    for path in extras:
        if not path.is_file():
            hits.append(f"missing:{path.relative_to(_ROOT)}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix == ".json":
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                hits.append(f"{path.relative_to(_ROOT)}: invalid json")
                continue
            blob = json.dumps(data, ensure_ascii=False)
            if _BRAND.search(blob) or "헤르메스" in blob:
                if re.search(r'(?<![A-Za-z_])Hermes(?![A-Za-z_])|헤르메스|(?<![A-Za-z_])HERMES(?![A-Za-z_0-9])', blob):
                    # Strip known protocol/runtime key names then recheck brand words.
                    scrub = blob
                    for k in (
                        "hermes_api_key",
                        "hermes_command",
                        "hermes_base_url",
                    ):
                        scrub = scrub.replace(k, "")
                    if _BRAND.search(scrub) or "헤르메스" in scrub:
                        hits.append(f"{path.relative_to(_ROOT)}: brand in catalog JSON")
            continue
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            continue
        docs = _docstring_lines(tree)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            lineno = getattr(node, "lineno", 0)
            if lineno in docs:
                continue
            s = node.value
            if not _BRAND.search(s) and "헤르메스" not in s:
                continue
            if _is_allowed(s):
                continue
            hits.append(f"{path.relative_to(_ROOT)}:{lineno}: {s[:120]!r}")
    return hits


def find_brand_hits() -> list[str]:
    return _ui_literal_hits() + _md_hits() + _extra_file_hits()


def main() -> int:
    hits = find_brand_hits()
    if hits:
        print("no_user_facing_agent_brand FAIL")
        for h in hits:
            print(h)
        return 1
    print("no_user_facing_agent_brand ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
