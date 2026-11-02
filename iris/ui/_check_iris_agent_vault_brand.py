"""Obsidian vault Iris Agent 브랜드 자검.

실행: .venv\\Scripts\\python.exe -m iris.ui._check_iris_agent_vault_brand
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERMES_DIR = ROOT / "obsidian-vault" / "Hermes"
IRIS_AGENT_DIR = ROOT / "obsidian-vault" / "Iris-Agent"
ACTIVE_HOME = r"%LOCALAPPDATA%\hermes"


def _is_disclaimer(line: str) -> bool:
    return "활성" in line and ("아님" in line or "아니다" in line)


def main() -> None:
    assert not HERMES_DIR.exists(), f"legacy folder still exists: {HERMES_DIR}"
    assert IRIS_AGENT_DIR.is_dir(), f"missing {IRIS_AGENT_DIR}"
    pages = list(IRIS_AGENT_DIR.glob("*.md"))
    assert len(pages) >= 7, f"expected >=7 pages, got {len(pages)}"

    overview = IRIS_AGENT_DIR / "00 - Iris Agent 개요.md"
    assert overview.is_file(), "missing overview"
    text = overview.read_text(encoding="utf-8")
    assert "Iris Agent" in text
    assert "~/.iris-light/agent" in text

    for page in pages:
        body = page.read_text(encoding="utf-8")
        for i, line in enumerate(body.splitlines(), 1):
            if ACTIVE_HOME in line and not _is_disclaimer(line):
                raise AssertionError(f"{page.name}:{i}: active-home {ACTIVE_HOME!r}")

    from iris.knowledge.obsidian_vault import ObsidianVault

    notes = ObsidianVault().list_notes()
    assert any(
        (n.folder or "").startswith("Iris-Agent") for n in notes
    ), "ObsidianVault has no Iris-Agent notes"
    assert not any(
        (n.folder or "") == "Hermes" or (n.folder or "").startswith("Hermes/")
        for n in notes
    ), "ObsidianVault still lists Hermes notes"

    print(
        "iris_agent_vault_brand ok",
        len(pages),
        "pages",
        sum(1 for n in notes if (n.folder or "").startswith("Iris-Agent")),
        "notes",
    )


if __name__ == "__main__":
    main()
