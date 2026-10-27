"""Sidecar NDJSON hangul survives when parent env lacks PYTHONUTF8."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from iris.engine._home import engine_python
from iris.engine.runtime import _sidecar_env
from iris.engine.types import _default_engine_home
from iris.system.win_subprocess import no_window_kwargs

_HANGUL = "안녕 이리스"


def main() -> None:
    home = _default_engine_home()
    python = engine_python(home)
    assert python is not None, "engine python missing"
    python_path = Path(python)

    saved = {
        key: os.environ.pop(key)
        for key in ("PYTHONUTF8", "PYTHONIOENCODING")
        if key in os.environ
    }
    try:
        env = _sidecar_env(home, python_path)
    finally:
        os.environ.update(saved)

    assert env.get("PYTHONUTF8") == "1", env.get("PYTHONUTF8")
    assert env.get("PYTHONIOENCODING") == "utf-8", env.get("PYTHONIOENCODING")

    code = (
        "import json, sys\n"
        f"print(json.dumps({{'t': 'delta', 'content': {_HANGUL!r}}}, "
        "ensure_ascii=False), flush=True)\n"
        "print(sys.stdout.encoding, file=sys.stderr, flush=True)\n"
    )
    proc = subprocess.Popen(
        [str(python_path), "-c", code],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(home),
        **no_window_kwargs(),
    )
    out, err = proc.communicate(timeout=15)
    assert proc.returncode == 0, (proc.returncode, err)
    assert "utf-8" in (err or "").lower(), err
    assert "\ufffd" not in (out or ""), repr(out)
    assert _HANGUL[:2] in (out or ""), repr(out)
    payload = json.loads((out or "").splitlines()[0])
    assert _HANGUL in str(payload.get("content", "")), payload
    print("sidecar utf8 hangul ok", payload["content"])


if __name__ == "__main__":
    main()
