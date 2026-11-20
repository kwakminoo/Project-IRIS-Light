"""Iris control skill SKILL.md format — no UTF-8 BOM, valid YAML frontmatter.

Fails when any integrations/iris-skills/iris-agent/*/SKILL.md:
  - starts with UTF-8 BOM (EF BB BF)
  - does not start with --- after BOM strip / utf-8-sig decode
  - frontmatter name: != parent directory name
  - frontmatter lacks description:

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_iris_skills_format
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_UTF8_BOM = b"\xef\xbb\xbf"
_REPO = Path(__file__).resolve().parents[2]
_SKILLS_ROOT = _REPO / "integrations" / "iris-skills" / "iris-agent"
_NAME_RE = re.compile(r"(?m)^name:\s*(.+?)\s*$")
_DESC_RE = re.compile(r"(?m)^description:\s*")


def skill_md_paths() -> list[Path]:
    if not _SKILLS_ROOT.is_dir():
        return []
    return sorted(_SKILLS_ROOT.glob("*/SKILL.md"))


def _frontmatter(text: str) -> str:
    if not text.startswith("---"):
        raise AssertionError("SKILL.md must start with ---")
    rest = text[3:]
    end = rest.find("\n---")
    if end < 0:
        raise AssertionError("SKILL.md missing closing --- frontmatter fence")
    return rest[:end]


def check_skill_md(path: Path) -> None:
    raw = path.read_bytes()
    rel = path.relative_to(_REPO).as_posix()
    parent = path.parent.name

    assert not raw.startswith(_UTF8_BOM), f"{rel}: UTF-8 BOM present (must start with --- bytes)"

    text = raw.decode("utf-8-sig")
    assert text.startswith("---"), f"{rel}: after decode must start with ---, got {text[:12]!r}"

    fm = _frontmatter(text)
    m = _NAME_RE.search(fm)
    assert m is not None, f"{rel}: frontmatter missing name:"
    name = m.group(1).strip().strip("\"'")
    assert name == parent, f"{rel}: name: {name!r} != parent dir {parent!r}"
    assert _DESC_RE.search(fm) is not None, f"{rel}: frontmatter missing description:"


def main() -> int:
    paths = skill_md_paths()
    if not paths:
        print(f"FAIL: no SKILL.md under {_SKILLS_ROOT}")
        return 1
    errors: list[str] = []
    for path in paths:
        try:
            check_skill_md(path)
        except AssertionError as exc:
            errors.append(str(exc))
    if errors:
        print("iris skills format FAIL")
        for err in errors:
            print(f"  {err}")
        return 1
    print(f"iris skills format ok ({len(paths)} SKILL.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
