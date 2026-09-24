"""브리지 resolvePath. 서버를 열지 않는다. --resolve-check 만 실행한다."""

from __future__ import annotations

import os
import subprocess
import tempfile

from iris.system.iris_ide_runtime import runtime_source_dir
from iris.system.node_runtime import node_executable


def main() -> None:
    node = node_executable()
    bridge = runtime_source_dir() / "bridge" / "standalone-bridge.js"
    with tempfile.TemporaryDirectory() as tmp:
        env = os.environ.copy()
        env["IRIS_IDE_WORKSPACE"] = tmp
        env["IRIS_BRIDGE_RESOLVE_CHECK"] = "1"
        proc = subprocess.run(
            [node, str(bridge), "--resolve-check"],
            cwd=tmp,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "resolvePath ok" in proc.stdout
    print("bridge resolvePath ok")


if __name__ == "__main__":
    main()
