"""iris-pdf skill: SKILL_NAMES + disk SKILL.md + SpeakTools routing table.

Observables:
  a) SKILL_NAMES contains iris-pdf
  b) integrations/iris-skills/iris-agent/iris-pdf/SKILL.md exists
  c) body names content.extract, content.dump_lab_scripts,
     wiki.import_content, note.export_pdf
  d) body forbids/warns local.read_file for PDF binary / lab dump
  e) format check (no BOM, name matches) still passes via shared helper
  f) MEMORY nudge (_BLOCK) teaches skill iris-pdf and keeps dump_lab

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_iris_pdf_skill
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SKILL = _REPO / "integrations" / "iris-skills" / "iris-agent" / "iris-pdf" / "SKILL.md"

_REQUIRED_ACTIONS = (
    "content.extract",
    "content.dump_lab_scripts",
    "wiki.import_content",
    "note.export_pdf",
)


def check_memory_nudge_teaches_iris_pdf() -> None:
    from iris.system import iris_agent_memory_nudge as nudge

    block = nudge._BLOCK
    assert "iris-pdf" in block, "MEMORY nudge _BLOCK must teach skill iris-pdf"
    assert "content.dump_lab_scripts" in block, (
        "MEMORY nudge _BLOCK must still mention content.dump_lab_scripts"
    )


def check_iris_pdf_skill() -> None:
    from iris.system.iris_agent_control_sync import SKILL_NAMES
    from iris.system._check_iris_skills_format import check_skill_md

    assert "iris-pdf" in SKILL_NAMES, "SKILL_NAMES missing iris-pdf"
    assert _SKILL.is_file(), f"missing {_SKILL.relative_to(_REPO).as_posix()}"

    text = _SKILL.read_text(encoding="utf-8-sig")
    for action in _REQUIRED_ACTIONS:
        assert action in text, f"iris-pdf SKILL.md must mention {action}"

    assert "local.read_file" in text, (
        "iris-pdf SKILL.md must mention local.read_file (forbid PDF binary / lab dump)"
    )
    lowered = text.lower()
    forbid_ok = any(
        marker in lowered
        for marker in (
            "do not local.read_file",
            "do not `local.read_file`",
            "never local.read_file",
            "never `local.read_file`",
            "not local.read_file",
            "forbid",
            "do not use `local.read_file`",
            "do not use local.read_file",
            "do not call local.read_file",
            "do not call `local.read_file`",
            "do not `local.read_file` the pdf",
            "do not local.read_file the pdf",
        )
    )
    # Accept common skill phrasing: "Do not local.read_file" / "Do not … local.read_file"
    if not forbid_ok:
        # Fall back: same paragraph/sentence as local.read_file contains do not / never / forbid
        for line in text.splitlines():
            if "local.read_file" not in line:
                continue
            ll = line.lower()
            if any(w in ll for w in ("do not", "don't", "never", "forbid", "금지", "하지 말")):
                forbid_ok = True
                break
    assert forbid_ok, (
        "iris-pdf SKILL.md must forbid/warn against local.read_file for PDF binary"
    )

    check_skill_md(_SKILL)
    check_memory_nudge_teaches_iris_pdf()


def main() -> int:
    try:
        check_iris_pdf_skill()
    except AssertionError as exc:
        print(f"iris-pdf skill FAIL: {exc}")
        return 1
    print("iris-pdf skill ok (incl. MEMORY nudge)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
