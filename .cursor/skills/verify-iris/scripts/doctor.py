"""Read-only: is this checkout worth driving for verify-iris?"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
VENV_PY = REPO / ".venv" / "Scripts" / "python.exe"
VENV_PYW = REPO / ".venv" / "Scripts" / "pythonw.exe"
CONTROL_DIR = Path.home() / ".iris-light"
RUN_MARKER = CONTROL_DIR / "verify-iris-run.json"


def _control_ping() -> dict:
    port_path = CONTROL_DIR / "control_port"
    token_path = CONTROL_DIR / "control_token"
    if not port_path.is_file() or not token_path.is_file():
        return {"live": False, "reason": "no control_port/token"}
    port = port_path.read_text(encoding="utf-8").strip()
    token = token_path.read_text(encoding="utf-8").strip()
    if not port or not token:
        return {"live": False, "reason": "empty control endpoint"}
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/invoke",
        data=json.dumps({"action": "ping", "args": {}}).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return {"live": True, "port": port, "ok": bool(body.get("ok")), "body": body}
    except Exception as exc:  # noqa: BLE001
        return {"live": False, "reason": str(exc), "port": port}


def main() -> int:
    report: dict = {
        "repo": str(REPO),
        "venv_python": VENV_PY.is_file(),
        "venv_pythonw": VENV_PYW.is_file(),
        "verify_run_marker": RUN_MARKER.is_file(),
        "shared_data_dir": str(CONTROL_DIR),
    }
    if not VENV_PY.is_file():
        report["ok"] = False
        report["error"] = "missing .venv\\Scripts\\python.exe"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    # Import smoke from the same interpreter the agent should use.
    sys.path.insert(0, str(REPO))
    try:
        import iris  # noqa: F401
        from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

        report["iris_import"] = True
        report["qt_webengine_helper"] = callable(ensure_qt_webengine_ready)
    except Exception as exc:  # noqa: BLE001
        report["ok"] = False
        report["iris_import"] = False
        report["error"] = str(exc)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    report["control"] = _control_ping()
    report["cwd"] = os.getcwd()
    report["ok"] = True
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
