"""IRIS IDE marketplace wiring — package manifest + Open VSX router."""

from __future__ import annotations

import json
from pathlib import Path

from iris.system.iris_ide_runtime import runtime_source_dir


def main() -> None:
    pkg_path = runtime_source_dir() / "package.json"
    data = json.loads(pkg_path.read_text(encoding="utf-8"))
    plugins = data.get("theiaPlugins") or {}
    assert plugins, "theiaPlugins must list vscode-builtin-extensions"
    assert "vscode-builtin-extensions" in plugins
    router = runtime_source_dir() / "ovsx-router-config.json"
    assert router.is_file(), "ovsx-router-config.json missing"
    router_data = json.loads(router.read_text(encoding="utf-8"))
    assert "open-vsx" in (router_data.get("registries") or {})
    print("iris_ide_marketplace check ok")


if __name__ == "__main__":
    main()
