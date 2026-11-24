"""Canonical Iris Agent settings and environment names only."""

from __future__ import annotations

from pathlib import Path

from iris.config.settings import Settings


def main() -> None:
    settings = Settings()
    for name in ("hermes_enabled", "hermes_command", "hermes_base_url", "hermes_api_key"):
        assert not hasattr(settings, name), name

    root = Path(__file__).resolve().parents[1]
    legacy_prefix = "IRIS_" + "HERMES_"
    offenders = [
        str(path.relative_to(root))
        for path in root.rglob("*.py")
        if path != Path(__file__) and legacy_prefix in path.read_text(encoding="utf-8")
    ]
    assert not offenders, offenders
    print("iris_agent_settings_names ok")


if __name__ == "__main__":
    main()
