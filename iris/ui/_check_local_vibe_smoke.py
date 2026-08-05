"""Local GUI smoke for chat-style vibe coding.

Run with Iris Light already open:
  python -m iris.ui._check_local_vibe_smoke
"""

from __future__ import annotations

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


def main() -> int:
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

    if not step("open_folder", invoke("ide.open_folder", {"path": str(root), "new_window": True})):
        return finish(root, steps)
    write = invoke(
        "project.write_file",
        {
            "project_root": str(root),
            "rel_path": "gugudan.py",
            "content": code,
            "open": True,
            "delay_ms": 1,
        },
    )
    if not step("write_file_typewriter", write):
        return finish(root, steps)
    run = invoke(
        "project.run",
        {"project_root": str(root), "file": "gugudan.py", "reveal_terminal": True},
        timeout=240.0,
    )
    log = root / ".iris" / "last_run.log"
    text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    step("run_in_ide_terminal", run, bool(run.get("ok")) and "9 x 9 = 81" in text)
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
    print(json.dumps({"wrote": str(OUT), **report}, ensure_ascii=False, indent=2))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
