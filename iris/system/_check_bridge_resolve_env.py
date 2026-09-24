"""IRIS_BRIDGE_RESOLVE_CHECK가 부모에 있어도 브리지는 listen 한다.

Theia는 띄우지 않는다. 브리지 프로세스만 잠시 띄우고 끝낸다.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from iris.system.iris_ide_runtime import runtime_source_dir
from iris.system.node_runtime import node_executable


def main() -> None:
    node = node_executable()
    bridge = runtime_source_dir() / "bridge" / "standalone-bridge.js"
    assert bridge.is_file(), bridge
    with tempfile.TemporaryDirectory() as tmp:
        env = os.environ.copy()
        env["IRIS_BRIDGE_RESOLVE_CHECK"] = "1"
        env["IRIS_IDE_WORKSPACE"] = tmp
        env.pop("IRIS_IDE_STATE_FILE", None)
        env["IRIS_IDE_BRIDGE_PORT"] = "0"
        proc = subprocess.Popen(
            [node, str(bridge)],
            cwd=tmp,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            assert proc.stdout is not None
            line = proc.stdout.readline()
            assert "listening" in line, line
            assert "resolvePath ok" not in line
            assert proc.poll() is None
        finally:
            proc.kill()
            proc.wait(timeout=5)
    print("bridge listens with IRIS_BRIDGE_RESOLVE_CHECK ok")


if __name__ == "__main__":
    main()
