"""IRIS IDE runtime unit checks."""

from __future__ import annotations

import os

from iris.system.iris_ide_runtime import (
    IrisIdeRuntimeManager,
    is_iris_ide_demo,
    runtime_install_dir,
    runtime_source_dir,
)
from iris.system.node_runtime import is_node_ready
from iris.system.setup_protocol import OPTIONAL_IDS


def main() -> None:
    assert "iris_ide" in OPTIONAL_IDS
    assert runtime_source_dir().joinpath("package.json").is_file()
    mgr = IrisIdeRuntimeManager()
    st = mgr.status()
    assert isinstance(st.installed, bool)
    ok_node, _ = is_node_ready()
    assert isinstance(ok_node, bool)
    demo = is_iris_ide_demo()
    os.environ["IRIS_IDE_DEMO"] = "1"
    assert IrisIdeRuntimeManager().is_installed()
    os.environ.pop("IRIS_IDE_DEMO", None)
    print("iris_ide_runtime check ok", runtime_install_dir(), "demo_was", demo)


if __name__ == "__main__":
    main()
