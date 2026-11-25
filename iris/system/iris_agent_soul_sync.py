"""Seed the default Iris identity when the Agent Home has no SOUL.md."""

from __future__ import annotations

from pathlib import Path

from iris.system.iris_agent_control_sync import iris_agent_home, project_root

_MARKER = "# IRIS Light Persona"


def repo_soul_path() -> Path:
    return project_root() / "integrations" / "hermes-soul" / "SOUL.md"


def iris_agent_soul_path(home: Path | None = None) -> Path:
    """제품 홈 SOUL만. 레거시 Hermes 홈은 보지 않는다."""
    if home is not None:
        return Path(home) / "SOUL.md"
    return iris_agent_home() / "SOUL.md"


def load_iris_persona_text() -> str:
    """Ollama 직행 등 SOUL을 안 읽는 경로용. 없으면 빈 문자열."""
    path = repo_soul_path()
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace").strip()


def ensure_soul(home: Path | None = None) -> str:
    src = repo_soul_path()
    if not src.is_file():
        return "soul skip: repo SOUL.md missing"
    desired = src.read_text(encoding="utf-8", errors="replace")
    if _MARKER not in desired:
        return "soul skip: repo SOUL.md missing Iris marker"
    desired_norm = desired.strip() + "\n"

    dst = iris_agent_soul_path(home)
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        with dst.open("x", encoding="utf-8") as stream:
            stream.write(desired_norm)
    except FileExistsError:
        return "soul preserved (existing identity)"
    return "soul initialized (Iris persona)"


if __name__ == "__main__":
    print(ensure_soul())
    text = load_iris_persona_text()
    assert _MARKER in text
    assert "아이리스" in text
    product = iris_agent_soul_path().read_text(encoding="utf-8", errors="replace")
    assert _MARKER in product
    assert "아이리스" in product
    assert "Hermes Agent" not in product
    assert "Nous Research" not in product
    print("ok", iris_agent_soul_path(), len(product), "chars")
