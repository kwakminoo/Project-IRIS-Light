"""integrations/iris-skills/README.md must match SpeakTools / skills / MCP reality.

Reads live SKILL_NAMES and action_catalog.json length — does not hardcode counts
in the assertions beyond the README text itself.

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_iris_skills_readme
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_README = _REPO / "integrations" / "iris-skills" / "README.md"
_CATALOG = _REPO / "iris" / "ui" / "control_actions" / "action_catalog.json"

_PDF_ACTIONS = (
    "content.extract",
    "content.dump_lab_scripts",
    "wiki.import_content",
    "note.export_pdf",
)

# Numbers next to these tokens are treated as claimed control-catalog sizes.
_CATALOG_CLAIM_RE = re.compile(
    r"(?P<n>\d+)\s*개|"
    r"(?P<n2>\d+)\s*(?:control[_\s-]?actions|catalog)|"
    r"(?:control[_\s-]?actions|catalog|ActionRegistry|get_catalog)[^\n]{0,40}?(?P<n3>\d+)",
    re.IGNORECASE,
)


def _catalog_len() -> int:
    data = json.loads(_CATALOG.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        actions = data.get("actions")
        if isinstance(actions, list):
            return len(actions)
        return len(data)
    raise AssertionError(f"unexpected action_catalog.json shape: {type(data)}")


def _claimed_catalog_counts(text: str) -> list[int]:
    found: list[int] = []
    for m in _CATALOG_CLAIM_RE.finditer(text):
        raw = m.group("n") or m.group("n2") or m.group("n3")
        if raw is None:
            continue
        found.append(int(raw))
    # Also catch bare "158개" style already covered; drop PHASE4/30-ish near SpeakTools
    # by requiring catalog-ish context (regex already does).
    return found


def check_iris_skills_readme() -> None:
    from iris.system.iris_agent_control_sync import SKILL_NAMES

    assert _README.is_file(), f"missing {_README.relative_to(_REPO).as_posix()}"
    text = _README.read_text(encoding="utf-8")

    assert "SpeakTools" in text, "README must mention SpeakTools"

    mcp_gone = any(
        marker in text
        for marker in (
            "iris-control MCP는 제품에 없다",
            "iris-control MCP는 완전 제거",
            "iris-control MCP 제거",
            "iris-control MCP는 제거",
            "TOOLS=[]",
            "TOOLS = []",
            "tombstone",
            "scrub",
            "제거",
        )
    ) and ("iris-control" in text)
    # Stronger: must say removed / not product / scrub / empty TOOLS
    mcp_contract = any(
        marker in text.lower()
        for marker in (
            "제품에 없다",
            "완전 제거",
            "항상 scrub",
            "scrub",
            "tools=[]",
            "tools = []",
            "tombstone",
            "not product",
            "removed",
        )
    )
    assert mcp_gone and mcp_contract, (
        "README must state iris-control MCP is removed / not product path "
        "(or TOOLS empty / scrub)"
    )

    for name in SKILL_NAMES:
        assert name in text, f"README must list skill {name!r} (from SKILL_NAMES)"

    assert "iris-pdf" in text, "README must mention iris-pdf"
    pdf_ok = "content.dump_lab_scripts" in text or all(a in text for a in _PDF_ACTIONS)
    assert pdf_ok, (
        "README must mention content.dump_lab_scripts "
        "(or all four PDF Speak actions)"
    )

    live = _catalog_len()
    for claimed in _claimed_catalog_counts(text):
        # Ignore small counts that are clearly SpeakTools / PHASE4 (~30) or skill counts
        if claimed <= max(40, len(SKILL_NAMES) + 5):
            continue
        assert claimed == live, (
            f"README claims control catalog count {claimed}, "
            f"but action_catalog.json has {live} — omit the number or use {live}"
        )


def main() -> int:
    try:
        check_iris_skills_readme()
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("ok: iris-skills README aligned with SKILL_NAMES / SpeakTools / catalog")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
