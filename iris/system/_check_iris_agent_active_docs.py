"""Current product docs must use canonical Iris Agent identifiers."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACTIVE_DOCS = (
    ROOT / "README.md",
    ROOT / "docs" / "domain.md",
    ROOT / "docs" / "ia" / "IA.md",
    ROOT / "docs" / "api" / "API-명세서.md",
    ROOT / "docs" / "guides" / "extending-iris.md",
)
BANNED = (
    "IRIS_" + "HERMES_",
    "settings." + "hermes_",
    "iris/infrastructure/" + "hermes_",
    "iris/system/" + "hermes_",
    "iris/ui/workers/" + "hermes_",
    "HermesClient",
    "HermesChatWorker",
    "resolve_hermes_inference",
)


def main() -> None:
    offenders = {
        str(path.relative_to(ROOT)): [needle for needle in BANNED if needle in path.read_text(encoding="utf-8")]
        for path in ACTIVE_DOCS
    }
    offenders = {path: needles for path, needles in offenders.items() if needles}
    assert not offenders, offenders
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Nous Hermes Agent" in readme
    print("iris_agent_active_docs ok")


if __name__ == "__main__":
    main()
