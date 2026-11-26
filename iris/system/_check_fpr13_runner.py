"""FPR13 evidence by layer, using existing Iris checks and verify-iris diagnostics.

L1 unit, L2 contract, L3 integration, L4 product E2E, L5 GUI E2E,
L6 lifecycle. Startup diagnostics carry no coverage layer. The report retains
unverified rows regardless of which execution profile is selected.

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_fpr13_runner
  .venv\\Scripts\\python.exe -m iris.system._check_fpr13_runner --contracts-only
  .venv\\Scripts\\python.exe -m iris.system._check_fpr13_runner --include-live
  .venv\\Scripts\\python.exe -m iris.system._check_fpr13_runner --include-gui
  .venv\\Scripts\\python.exe -m iris.system._check_fpr13_runner --include-lifecycle
"""

from __future__ import annotations

import argparse
import json
import os
import socket
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

# kind selects when an executable check runs. layer records what it proves.
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
        "layer": "L1",
        "command": ["-m", "iris.ui.chat._check_model_picker_roster"],
        "requires": [],
    },
    {
        "id": "c14_user_branding",
        "title": "Iris Agent branding on user-facing paths",
        "kind": "contract",
        "command": ["-m", "iris.ui._check_hermes_user_branding_p4"],
        "requires": [],
    },
    {
        "id": "l01_general_chat",
        "title": "Headless Owned Engine HELLO with local model",
        "kind": "live",
        "layer": "L3",
        "command": ["-m", "iris.system._check_owned_live_hello"],
        "requires": ["model"],
    },
    {
        "id": "doctor_startup",
        "title": "verify-iris startup diagnostic",
        "kind": "live",
        "layer": "diagnostic",
        "command": [
            str(REPO / ".cursor" / "skills" / "verify-iris" / "scripts" / "doctor.py"),
        ],
        "requires": [],
    },
    {
        "id": "control_http_contract",
        "title": "Temporary Control HTTP server and fake invoker contract",
        "kind": "live",
        "layer": "L2",
        "command": ["-m", "iris.system._check_control_http_contract"],
        "requires": ["loopback bind"],
    },
    {
        "id": "l04_shell_model",
        "title": "Headless Owned shell marker and native shell action with fixture approval",
        "kind": "live",
        "layer": "L3",
        "command": ["-m", "iris.system._check_owned_live_shell"],
        "requires": ["model"],
    },
    {
        "id": "ide_product_control",
        "title": "Isolated product Control API and installed IDE workflow",
        "kind": "product",
        "layer": "L4",
        "command": ["-m", "iris.ui._check_local_vibe_smoke"],
        "requires": ["running isolated IRIS", "installed IDE", "loopback bind"],
    },
    {
        "id": "wiki_browser_gui",
        "title": "Product Wiki and Browser clicks with local WebEngine navigation",
        "kind": "gui",
        "layer": "L5",
        "command": ["-m", "iris.ui._check_fpr_product_gui", "browser"],
        "requires": ["interactive Qt desktop", "WebEngine"],
    },
    {
        "id": "process_approval_gui",
        "title": "Product GUI process approval, start and wait",
        "kind": "gui",
        "layer": "L5",
        "command": ["-m", "iris.ui._check_fpr_product_gui", "process"],
        "requires": ["interactive Qt desktop", "WebEngine", "loopback bind"],
    },
    {
        "id": "installer_lifecycle",
        "title": "Clean product install, product update and recovery",
        "kind": "lifecycle",
        "layer": "L6",
        "command": ["-m", "iris.system._check_owned_lifecycle"],
        "requires": ["isolated home", "installable engine", "local Ollama model"],
    },
]
for _scenario in SCENARIOS:
    _scenario.setdefault("layer", "L2")


def _python() -> Path:
    venv = REPO / ".venv" / "Scripts" / "python.exe"
    return venv if venv.is_file() else Path(sys.executable)


def _live_enabled(ns: argparse.Namespace) -> bool:
    if ns.include_live:
        return True
    return (os.environ.get(LIVE_ENV) or "").strip().lower() in {"1", "true", "yes", "on"}


def _run_one(
    py: Path, scenario: dict[str, Any], log_dir: Path, *, product_home: Path | None = None
) -> dict[str, Any]:
    row = dict(scenario)
    cmd = [str(py), *list(scenario["command"])]
    log_path = log_dir / f"{scenario['id']}.log"
    env = None
    if product_home is not None:
        env = {**os.environ, "USERPROFILE": str(product_home), "HOME": str(product_home)}
    t0 = time.monotonic()
    proc = subprocess.run(
        cmd,
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
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
    row["log_path"] = log_path.as_posix()
    row["elapsed_s"] = elapsed
    row["status"] = "PASS" if proc.returncode == 0 else "FAIL"
    return row


def _blocked_reason(scenario: dict[str, Any]) -> str:
    if "loopback bind" in scenario["requires"]:
        try:
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
        except OSError as exc:
            return f"Loopback bind unavailable ({exc})"
    return ""


def _markdown_table(result: dict[str, Any]) -> str:
    lines = [
        "# FPR13 scenario results",
        "",
        f"- started_at: `{result['started_at']}`",
        f"- summary: `{json.dumps(result['summary'], ensure_ascii=False)}`",
        "",
        "| id | title | layer | requires | status | exit_code | log | notes |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in result["scenarios"]:
        req = ",".join(s.get("requires") or []) or "—"
        lines.append(
            "| {id} | {title} | {layer} | {req} | {status} | {exit} | {log} | {notes} |".format(
                id=s["id"],
                title=s["title"].replace("|", "/"),
                layer=s["layer"],
                req=req,
                status=s.get("status", ""),
                exit="" if s.get("exit_code") is None else s["exit_code"],
                log=s.get("log_path") or "—",
                notes=s.get("notes", "").replace("|", "/"),
            )
        )
    lines.append("")
    lines.append("Each PASS covers the evidence layer and scenario in its row.")
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
    p.add_argument("--include-gui", action="store_true", help="Run UI automation on this desktop")
    p.add_argument(
        "--include-lifecycle",
        action="store_true",
        help="Run L6 owned install/update/recovery (long; not part of contracts-only)",
    )
    p.add_argument(
        "--out-dir",
        default="",
        help="Output directory (default: .tmp/fpr13)",
    )
    p.add_argument(
        "--product-home",
        type=Path,
        help="Home of an already running IRIS instance on a disposable test profile",
    )
    ns = p.parse_args(argv)
    if ns.product_home is not None:
        ns.product_home = ns.product_home.resolve()
        if ns.product_home == Path.home().resolve() or not ns.product_home.is_dir():
            p.error("--product-home must be a separate test user home")

    out = Path(ns.out_dir).resolve() if ns.out_dir else OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    log_dir = out / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    py = _python()
    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    run_live = _live_enabled(ns) and not ns.contracts_only

    rows: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        kind = scenario["kind"]
        note = ""
        if kind == "manual":
            note = "Requires separate test evidence"
        elif kind == "live" and not run_live:
            note = f"Set {LIVE_ENV}=1 or --include-live"
        elif kind == "gui" and (ns.contracts_only or not ns.include_gui):
            note = "Use --include-gui on an interactive desktop"
        elif kind == "lifecycle" and (ns.contracts_only or not ns.include_lifecycle):
            note = "Use --include-lifecycle (isolated install; long-running)"
        elif kind == "product" and (ns.contracts_only or ns.product_home is None):
            note = "Start IRIS with an isolated home and pass --product-home"
        if note:
            rows.append(dict(scenario, status="UNVERIFIED", notes=note))
            print(f"[skip] {scenario['id']} ({note})")
            continue
        if reason := _blocked_reason(scenario):
            rows.append(dict(scenario, status="BLOCKED", notes=reason))
            print(f"[blocked] {scenario['id']} ({reason})")
            continue
        print(f"[run ] {scenario['id']} …", flush=True)
        rows.append(_run_one(py, scenario, log_dir, product_home=ns.product_home if kind == "product" else None))
        print(f"       → {rows[-1]['status']} exit={rows[-1]['exit_code']}", flush=True)

    statuses = ("PASS", "FAIL", "UNVERIFIED", "BLOCKED")
    summary = {
        "total": len(rows),
        "live_enabled": run_live,
        "python": str(py),
        **{status.lower(): sum(row["status"] == status for row in rows) for status in statuses},
        "by_layer": {
            layer: {
                status: sum(row["layer"] == layer and row["status"] == status for row in rows)
                for status in statuses
            }
            for layer in dict.fromkeys(row["layer"] for row in rows)
        },
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
    print(f"wrote {json_path} and {md_path}")
    return 1 if summary["fail"] or summary["blocked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
