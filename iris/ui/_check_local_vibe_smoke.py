"""Product Control smoke for a running IRIS desktop and a disposable workspace.

Select IRIS IDE in the test profile and approve the write and run in the UI:
  python -m iris.ui._check_local_vibe_smoke

Use --ide cursor with a Cursor test profile to retain the file-watch scenario.
"""

from __future__ import annotations

import argparse
import json
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".iris_light_test_tmp" / "local_vibe_smoke_report.json"


def _endpoint() -> tuple[str, str]:
    d = Path.home() / ".iris-light"
    return (
        f"http://127.0.0.1:{(d / 'control_port').read_text(encoding='utf-8').strip()}",
        (d / "control_token").read_text(encoding="utf-8").strip(),
    )


def invoke(action: str, args: dict | None = None, *, timeout: float = 180.0) -> dict:
    base, token = _endpoint()
    data = json.dumps({"action": action, "args": args or {}}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        base + "/v1/invoke",
        data=data,
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ide", choices=("iris_ide", "cursor"), default="iris_ide")
    expected_ide = parser.parse_args(argv).ide
    root = Path(tempfile.mkdtemp(prefix="iris-vibe-smoke-")).resolve()
    code = "\n".join(
        [
            "for n in range(2, 10):",
            "    print(f'=== {n}단 ===')",
            "    for i in range(1, 10):",
            "        print(f'{n} x {i} = {n * i}')",
            "",
        ]
    )
    steps: list[dict] = []

    def step(name: str, result: dict, passed: bool | None = None) -> bool:
        ok = bool(result.get("ok")) if passed is None else bool(passed)
        steps.append({"name": name, "pass": ok, "result": result})
        return ok

    def result_of(response: dict) -> dict:
        result = response.get("result")
        return result if isinstance(result, dict) else {}

    opened = invoke("ide.open_folder", {"path": str(root), "new_window": True})
    opened_result = result_of(opened)
    if not step(
        "open_exact_ide_workspace", opened,
        bool(opened.get("ok")) and opened_result.get("ide_id") == expected_ide
        and opened_result.get("path") == str(root),
    ):
        return finish(root, steps)
    write = invoke(
        "project.write_file",
        {
            "project_root": str(root),
            "rel_path": "gugudan.py",
            "content": code,
            "open": True,
            "chunk_chars": 12,
            "chunk_delay_ms": 70,
        },
    )
    write_result = result_of(write)
    editor_visible = (
        write_result.get("via") == "iris_ide_bridge" and write_result.get("visible") is True
        if expected_ide == "iris_ide"
        else write_result.get("input_mode") == "file_watch" and write_result.get("chunks", 0) >= 3
    )
    if not step(
        "write_file_in_ide" if expected_ide == "iris_ide" else "write_file_live_stream",
        write,
        bool(write.get("ok")) and editor_visible and (root / "gugudan.py").read_text("utf-8") == code,
    ):
        return finish(root, steps)
    marker = "IRIS_IDE_VIBE_EDITED"
    if expected_ide == "iris_ide":
        edited = code + f"print('{marker}')\n"
        edit = invoke("ide.edit", {"op": "document", "path": "gugudan.py", "text": edited})
        if not step("edit_in_monaco", edit, bool(edit.get("ok")) and result_of(edit).get("via") == "editor"):
            return finish(root, steps)
        reopened = invoke("ide.open_folder", {"path": str(root), "new_window": False})
        if not step("reopen_same_workspace", reopened, bool(reopened.get("ok")) and result_of(reopened).get("path") == str(root)):
            return finish(root, steps)
        overwrite = invoke(
            "project.write_file",
            {"project_root": str(root), "rel_path": "gugudan.py", "content": "print('overwrite')\n"},
        )
        if not step(
            "protect_unsaved_editor", overwrite,
            not overwrite.get("ok") and "dirty" in str(overwrite.get("error") or "").lower(),
        ):
            return finish(root, steps)
        saved = invoke("ide.save", {"path": "gugudan.py"})
        file = root / "gugudan.py"
        if not step(
            "save_preserved_editor", saved,
            bool(saved.get("ok")) and result_of(saved).get("via") == "editor"
            and file.is_file() and file.read_text("utf-8") == edited,
        ):
            return finish(root, steps)
        edited += "# confirmed existing file write\n"
        overwrite = invoke(
            "project.write_file",
            {"project_root": str(root), "rel_path": "gugudan.py", "content": edited},
        )
        if not step(
            "write_clean_existing_file", overwrite,
            bool(overwrite.get("ok")) and result_of(overwrite).get("content_match") is True,
        ):
            return finish(root, steps)
        read = invoke("project.read_file", {"project_root": str(root), "rel_path": "gugudan.py"})
        if not step("read_edited_file", read, bool(read.get("ok")) and result_of(read).get("content") == edited):
            return finish(root, steps)

    run = invoke(
        "project.run",
        {"project_root": str(root), "file": "gugudan.py", "reveal_terminal": True},
        timeout=240.0,
    )
    log = root / ".iris" / "last_run.log"
    text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    run_result = result_of(run)
    mirror_ok = expected_ide != "iris_ide" or (
        marker in text and run_result.get("ide_terminal") == "ok" and run_result.get("revealed") is True
    )
    step(
        "run_in_ide_terminal", run,
        bool(run.get("ok")) and run_result.get("exit_code") == 0 and "9 x 9 = 81" in text and mirror_ok,
    )
    return finish(root, steps)


def finish(root: Path, steps: list[dict]) -> int:
    report = {
        "project_root": str(root),
        "passed": sum(1 for s in steps if s["pass"]),
        "total": len(steps),
        "steps": steps,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), **report}, ensure_ascii=True, indent=2))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
