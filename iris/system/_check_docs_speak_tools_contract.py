"""Docs must describe SpeakTools product path, not obsolete iris-control MCP triple.

Fails if the three named docs still contain iris_get_state / iris_get_catalog /
iris_invoke as current product wording (prefer zero occurrences).

Run: .venv\\Scripts\\python.exe -m iris.system._check_docs_speak_tools_contract
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DOCS = (
    "docs/research/aside/04_IRIS_GAP_ANALYSIS.md",
    "docs/research/aside/05_IMPLEMENTATION_PLAN.md",
    "docs/api/API-명세서.md",
)

BANNED = (
    "iris_get_state",
    "iris_get_catalog",
    "iris_invoke",
)


def main() -> None:
    hits: list[str] = []
    for rel in DOCS:
        text = (ROOT / rel).read_text(encoding="utf-8")
        for needle in BANNED:
            if needle in text:
                for i, line in enumerate(text.splitlines(), 1):
                    if needle in line:
                        hits.append(f"{rel}:{i}: {needle}")
    assert not hits, (
        "obsolete MCP triple still in docs (use SpeakTools get_state/"
        "get_catalog/control.invoke):\n" + "\n".join(hits)
    )
    print("docs_speak_tools_contract ok", len(DOCS), "files")


if __name__ == "__main__":
    main()
