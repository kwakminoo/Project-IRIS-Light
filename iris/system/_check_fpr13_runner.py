"""13+FPR scenario runner — bundles existing iris ``_check_*`` / verify-iris pieces.

Does not invent a new test framework. Runs known ``python -m iris...`` modules,
writes a fillable results table under ``.tmp/fpr13/``.

Kinds:
  contract — offline; any fail → process exit non-zero
  live     — skipped unless ``IRIS_FPR13_LIVE=1`` (or ``--include-live``)

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_fpr13_runner
  .venv\\Scripts\\python.exe -m iris.system._check_fpr13_runner --contracts-only
  .venv\\Scripts\\python.exe -m iris.system._check_fpr13_runner --include-live
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from iris.system.win_subprocess import no_window_kwargs

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / ".tmp" / "fpr13"
LIVE_ENV = "IRIS_FPR13_LIVE"

# Scenario: {id, title, kind, command, requires, status}
# command = argv after the interpreter (usually ``-m iris...``).
SCENARIOS: list[dict[str, Any]] = [
    # --- 13 core contracts (FGC 3a + shell speak) ---
    {
        "id": "c01_tool_contract",
        "title": "Unified tool contract (SpeakAllowlist / schemas)",
        "kind": "contract",
        "command": ["-m", "iris.infrastructure._check_tool_contract"],
        "requires": [],
    },
    {
        "id": "c02_speak_surface_shell",
        "title": "Speak surface shell coerce / shell.run",
        "kind": "contract",
        "command": ["-m", "iris.infrastructure._check_speak_surface_shell"],
        "requires": [],
    },
    {
        "id": "c03_hermes_disabled",
        "title": "Native Hermes tool registry disabled",
        "kind": "contract",
        "command": ["-m", "iris.infrastructure._check_native_tool_hermes_disabled"],
        "requires": [],
    },
    {
        "id": "c04_absorbed_tool_wire",
        "title": "Absorbed tool wire (home/ide)",
        "kind": "contract",
        "command": ["-m", "iris.infrastructure._check_absorbed_tool_wire"],
        "requires": [],
    },
    {
        "id": "c05_request_approval",
        "title": "Request approval ledger / consume",
        "kind": "contract",
        "command": ["-m", "iris.system._check_request_approval"],
        "requires": [],
    },
    {
        "id": "c06_process_manage",
        "title": "process.manage plan→approve→start",
        "kind": "contract",
        "command": ["-m", "iris.system._check_process_manage"],
        "requires": [],
    },
    {
        "id": "c07_browser_intent",
        "title": "Browser intent forge / source=human",
        "kind": "contract",
        "command": ["-m", "iris.browser._check_intent"],
        "requires": [],
    },
    {
        "id": "c08_email_compose",
        "title": "Email compose prefill (sent=false)",
        "kind": "contract",
        "command": ["-m", "iris.ui.workspaces._check_email_compose"],
        "requires": [],
    },
    {
        "id": "c09_workspace_environment",
        "title": "Workspace environment vs Agent Core",
        "kind": "contract",
        "command": ["-m", "iris.system._check_workspace_environment"],
        "requires": [],
    },
    {
        "id": "c10_shell_gate",
        "title": "Shell gate / Shell Box contract",
        "kind": "contract",
        "command": ["-m", "iris.ui.chat._check_shell_gate"],
        "requires": [],
    },
    {
        "id": "c11_agent_confirm_path",
        "title": "Agent confirm_required path",
        "kind": "contract",
        "command": ["-m", "iris.ui._check_agent_confirm_path"],
        "requires": [],
    },
    {
        "id": "c12_chat_landing",
        "title": "Chat landing / fail land contract",
        "kind": "contract",
        "command": ["-m", "iris.ui._check_chat_landing_contract"],
        "requires": [],
    },
    {
        "id": "c13_execution_context",
        "title": "ExecutionContext host overlay bind",
        "kind": "contract",
        "command": ["-m", "iris.system._check_execution_context"],
        "requires": [],
    },
    # --- FPR contract extras ---
    {
        "id": "fpr_execution_runtime",
        "title": "FPR: execution runtime ring / cancel",
        "kind": "contract",
        "command": ["-m", "iris.system._check_execution_runtime"],
        "requires": [],
    },
    {
        "id": "fpr_transcript_h1",
        "title": "FPR: transcript H1 / scrollbar CSS",
        "kind": "contract",
        "command": ["-m", "iris.ui.chat._check_transcript_h1"],
        "requires": [],
    },
    {
        "id": "fpr_model_picker_roster",
        "title": "FPR: model picker roster",
        "kind": "contract",
        "command": ["-m", "iris.ui.chat._check_model_picker_roster"],
        "requires": [],
    },
    # --- Live (default skip) — fillable rows for GUI/model evidence ---
    {
        "id": "l01_general_chat",
        "title": "Live #1: Owned HELLO (headless Engine, no IDE bridge)",
        "kind": "live",
        "command": ["-m", "iris.system._check_owned_live_hello"],
        "requires": ["model"],
    },
    {
        "id": "l02_browser_gui",
        "title": "Live #2–3: Wiki/Browser GUI path",
        "kind": "live",
        "command": [
            str(REPO / ".cursor" / "skills" / "verify-iris" / "scripts" / "doctor.py"),
        ],
        "requires": ["gui"],
    },
    {
        "id": "l03_process_gui",
        "title": "Live #12: process start→wait via Control",
        "kind": "live",
        "command": ["-m", "iris.system._check_control_http_contract"],
        "requires": ["gui", "approval"],
    },
    {
        "id": "l04_shell_model",
        "title": "Live: Owned shell.run + marker (tool_choice=required)",
        "kind": "live",
        "command": ["-m", "iris.system._check_owned_live_shell"],
        "requires": ["model"],
    },
]


def _python() -> Path:
    venv = REPO / ".venv" / "Scripts" / "python.exe"
    return venv if venv.is_file() else Path(sys.executable)


def _live_enabled(ns: argparse.Namespace) -> bool:
    if ns.include_live:
        return True
    return (os.environ.get(LIVE_ENV) or "").strip().lower() in {"1", "true", "yes", "on"}


def _run_one(py: Path, scenario: dict[str, Any], log_dir: Path) -> dict[str, Any]:
    row = dict(scenario)
    row.setdefault("status", "pending")
    cmd = [str(py), *list(scenario["command"])]
    log_path = log_dir / f"{scenario['id']}.log"
    t0 = time.monotonic()
    proc = subprocess.run(
        cmd,
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        **no_window_kwargs(),
    )
    elapsed = round(time.monotonic() - t0, 3)
    body = (
        f"$ {' '.join(cmd)}\n"
        f"exit={proc.returncode} elapsed_s={elapsed}\n\n"
        f"--- stdout ---\n{proc.stdout or ''}\n"
        f"--- stderr ---\n{proc.stderr or ''}\n"
    )
    log_path.write_text(body, encoding="utf-8")
    row["exit_code"] = int(proc.returncode)
    row["log_path"] = str(log_path.relative_to(REPO)).replace("\\", "/")
    row["elapsed_s"] = elapsed
    row["status"] = "pass" if proc.returncode == 0 else "fail"
    return row


def _markdown_table(result: dict[str, Any]) -> str:
    lines = [
        "# FPR13 scenario results",
        "",
        f"- started_at: `{result['started_at']}`",
        f"- summary: `{json.dumps(result['summary'], ensure_ascii=False)}`",
        "",
        "| id | title | kind | requires | status | exit_code | log | notes |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in result["scenarios"]:
        req = ",".join(s.get("requires") or []) or "—"
        notes = ""
        if s.get("status") == "skipped":
            notes = f"set {LIVE_ENV}=1 or --include-live"
        elif s.get("status") == "fail":
            notes = "see log"
        lines.append(
            "| {id} | {title} | {kind} | {req} | {status} | {exit} | {log} | {notes} |".format(
                id=s["id"],
                title=s["title"].replace("|", "/"),
                kind=s["kind"],
                req=req,
                status=s.get("status", ""),
                exit="" if s.get("exit_code") is None else s["exit_code"],
                log=s.get("log_path") or "—",
                notes=notes,
            )
        )
    lines.append("")
    lines.append("Fill live rows after enabling live runs; keep contract failures red until fixed.")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="13+FPR scenario runner (existing _check_* only)")
    p.add_argument(
        "--contracts-only",
        action="store_true",
        help="Run contract scenarios only (default behavior when live env unset)",
    )
    p.add_argument(
        "--include-live",
        action="store_true",
        help=f"Also run live scenarios (same as {LIVE_ENV}=1)",
    )
    p.add_argument(
        "--out-dir",
        default="",
        help="Output directory (default: .tmp/fpr13)",
    )
    ns = p.parse_args(argv)

    out = Path(ns.out_dir) if ns.out_dir else OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    log_dir = out / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    py = _python()
    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    run_live = _live_enabled(ns) and not ns.contracts_only

    rows: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        kind = scenario["kind"]
        if kind == "live" and not run_live:
            row = dict(scenario)
            row["status"] = "skipped"
            row["exit_code"] = None
            row["log_path"] = ""
            row["elapsed_s"] = 0
            rows.append(row)
            print(f"[skip] {scenario['id']} (live; set {LIVE_ENV}=1)")
            continue
        if ns.contracts_only and kind != "contract":
            continue
        print(f"[run ] {scenario['id']} …", flush=True)
        rows.append(_run_one(py, scenario, log_dir))
        print(f"       → {rows[-1]['status']} exit={rows[-1]['exit_code']}", flush=True)

    passed = sum(1 for r in rows if r.get("status") == "pass")
    failed = sum(1 for r in rows if r.get("status") == "fail")
    skipped = sum(1 for r in rows if r.get("status") == "skipped")
    summary = {
        "total": len(rows),
        "pass": passed,
        "fail": failed,
        "skipped": skipped,
        "live_enabled": run_live,
        "python": str(py),
    }
    result = {
        "started_at": started,
        "scenarios": rows,
        "summary": summary,
    }

    json_path = out / "results.json"
    md_path = out / "results.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_markdown_table(result), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    print(f"wrote {json_path.relative_to(REPO)} and {md_path.relative_to(REPO)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
