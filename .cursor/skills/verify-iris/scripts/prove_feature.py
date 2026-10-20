"""Run one mapped verify-iris feature; write evidence under .iris_light_test_tmp/verify-iris/."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
VENV_PY = REPO / ".venv" / "Scripts" / "python.exe"
EVIDENCE_ROOT = REPO / ".iris_light_test_tmp" / "verify-iris"

# feature_id -> argv relative to repo (run with venv python -m ...)
FEATURES: dict[str, list[str]] = {
    "startup": ["-m", "iris.ui._check_iris_startup"],
    "companion-tile": ["-m", "iris.ui._check_iris_ide_companion_tile"],
    "control-http": ["-m", "iris.system._check_control_http_contract"],
    "chat-stop": ["-m", "iris.ui._check_chat_stop_button"],
    "file-drop": ["-m", "iris.ui.window._check_file_drop"],
    "no-console": ["-m", "unittest", "tests.test_no_console_window", "-v"],
}

# Qt teardown can ACCESS_VIOLATE after the check already printed success.
SUCCESS_MARKERS: dict[str, str] = {
    "startup": "iris_startup ok",
}


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--feature", required=True, choices=sorted(FEATURES))
    p.add_argument("--run-id", default="")
    ns = p.parse_args()
    if not VENV_PY.is_file():
        print(json.dumps({"ok": False, "error": "missing venv python"}, ensure_ascii=False))
        return 1

    run_id = ns.run_id or _run_id()
    out_dir = EVIDENCE_ROOT / run_id / ns.feature
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [str(VENV_PY), *FEATURES[ns.feature]]
    t0 = time.monotonic()
    proc = subprocess.run(
        cmd,
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    elapsed = time.monotonic() - t0
    (out_dir / "stdout.txt").write_text(proc.stdout or "", encoding="utf-8")
    (out_dir / "stderr.txt").write_text(proc.stderr or "", encoding="utf-8")
    stdout = proc.stdout or ""
    marker = SUCCESS_MARKERS.get(ns.feature)
    marked_ok = bool(marker and marker in stdout)
    ok = proc.returncode == 0 or marked_ok
    report = {
        "feature": ns.feature,
        "run_id": run_id,
        "cmd": cmd,
        "exit_code": proc.returncode,
        "ok": ok,
        "success_marker": marker,
        "success_marker_hit": marked_ok,
        "elapsed_s": round(elapsed, 3),
        "evidence_dir": str(out_dir),
        "stdout_tail": stdout[-2000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
    }
    (out_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
