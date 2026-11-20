"""Live control HTTP: list_files → read_file → ide.edit (Iris must be running).

Uses the bound IDE workspace_root from get_state (not profile project_root).
Writes the scratch with open=false so workspace-align does not hang the turn.

  python -m iris.ui._check_project_read_list_edit_live
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".iris_light_test_tmp" / "project_read_list_edit_live_report.json"
SCRATCH = f"_iris_read_edit_{int(time.time())}.txt"


def _endpoint() -> tuple[str, str]:
    d = Path.home() / ".iris-light"
    return (
        f"http://127.0.0.1:{(d / 'control_port').read_text(encoding='utf-8').strip()}",
        (d / "control_token").read_text(encoding="utf-8").strip(),
    )


def invoke(action: str, args: dict | None = None, *, timeout: float = 60.0) -> dict:
    base, token = _endpoint()
    data = json.dumps({"action": action, "args": args or {}}, ensure_ascii=False).encode(
        "utf-8"
    )
    req = urllib.request.Request(
        base + "/v1/invoke",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"http": resp.status, **json.loads(resp.read().decode("utf-8"))}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {"raw": raw}
        return {"http": exc.code, "ok": False, **body}
    except Exception as exc:  # noqa: BLE001
        return {"http": 0, "ok": False, "error": str(exc)}


def main() -> int:
    steps: list[dict] = []

    def step(name: str, result: dict, passed: bool | None = None) -> bool:
        ok = bool(result.get("ok")) if passed is None else bool(passed)
        steps.append({"name": name, "pass": ok, "result": result})
        return ok

    state = invoke("get_state")
    body = state.get("result") if isinstance(state.get("result"), dict) else {}
    session = body.get("ide_session") if isinstance(body.get("ide_session"), dict) else {}
    root = str(session.get("workspace_root") or "").strip()
    if not step(
        "get_state",
        state,
        bool(state.get("ok"))
        and bool(root)
        and body.get("ui_mode") == "ide_companion"
        and bool(session.get("active")),
    ):
        return finish(root, steps)

    # Disk seed only — project.write_file may block on work_root↔IDE align.
    scratch_path = Path(root) / SCRATCH
    try:
        scratch_path.write_text("alpha\n", encoding="utf-8")
        disk_ok = scratch_path.is_file()
    except OSError as exc:
        disk_ok = False
        steps.append(
            {
                "name": "write_scratch_disk",
                "pass": False,
                "result": {"ok": False, "error": str(exc)},
            }
        )
        return finish(root, steps)
    if not step(
        "write_scratch_disk",
        {"ok": disk_ok, "path": str(scratch_path)},
        disk_ok,
    ):
        return finish(root, steps)

    listed = invoke(
        "project.list_files",
        {"project_root": root, "query": SCRATCH},
        timeout=30.0,
    )
    payload = listed.get("result") if isinstance(listed.get("result"), dict) else {}
    files = payload.get("files") or []
    flat = " ".join(str(x) for x in files) if isinstance(files, list) else str(files)
    if not step("list_files", listed, bool(listed.get("ok")) and SCRATCH in flat):
        return finish(root, steps)

    read = invoke(
        "project.read_file",
        {"project_root": root, "rel_path": SCRATCH},
        timeout=30.0,
    )
    read_body = read.get("result") if isinstance(read.get("result"), dict) else {}
    read_text = str(read_body.get("content") or "").replace("\r\n", "\n")
    if not step(
        "read_file",
        read,
        bool(read.get("ok")) and read_text == "alpha\n",
    ):
        return finish(root, steps)

    opened = invoke(
        "ide.open_file",
        {"project_root": root, "rel_path": SCRATCH},
        timeout=60.0,
    )
    if not step("open_file", opened):
        return finish(root, steps)

    # Absolute path: relative path also hangs when applyTextEdit stalls (measured).
    edited = invoke(
        "ide.edit",
        {"op": "apply", "path": str(scratch_path), "text": "alpha\nbeta\n"},
        timeout=45.0,
    )
    edit_body = edited.get("result") if isinstance(edited.get("result"), dict) else {}
    step(
        "ide_edit",
        edited,
        bool(edited.get("ok")) and edit_body.get("via") == "editor",
    )

    try:
        scratch_path.unlink(missing_ok=True)
    except OSError:
        pass
    return finish(root, steps)


def finish(root: str, steps: list[dict]) -> int:
    report = {
        "project_root": root,
        "scratch": SCRATCH,
        "passed": sum(1 for s in steps if s["pass"]),
        "total": len(steps),
        "steps": steps,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), **report}, ensure_ascii=False, indent=2))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
