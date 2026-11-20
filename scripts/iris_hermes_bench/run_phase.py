#!/usr/bin/env python3
"""Run one bench phase for hermes and/or iris arms. Default is dry-run."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib import (
    WORK_ROOT,
    grade_product_effect,
    grade_text,
    iris_assistant_after,
    iris_invoke,
    iris_max_message_id,
    load_cases,
    snapshot_product,
    utc_now,
    write_json,
)


def load_manifest(run_dir: Path) -> dict[str, Any]:
    return json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))


def result_path(run_dir: Path, arm: str, case_id: str) -> Path:
    return run_dir / "results" / arm / f"{case_id}.json"


def run_hermes(manifest: dict[str, Any], prompt: str, out_txt: Path) -> tuple[str, str | None]:
    env = os.environ.copy()
    env["HERMES_HOME"] = manifest["hermes_home"]
    cmd = [
        manifest["hermes_bin"],
        "chat",
        "-q",
        prompt,
        "--oneshot",
        "-Q",
        "-m",
        manifest["model"],
        "--provider",
        manifest.get("provider", "custom"),
        "--base-url",
        manifest["base_url"],
        "--api-key",
        manifest.get("api_key", "ollama"),
        "--max-turns",
        str(manifest.get("max_turns", 12)),
        "--ignore-user-config",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=manifest.get("iris_turn_timeout_s", 300),
            check=False,
        )
    except subprocess.TimeoutExpired:
        out_txt.write_text("", encoding="utf-8")
        return "", "timeout"
    text = (proc.stdout or "").strip()
    if not text:
        text = (proc.stderr or "").strip()
    out_txt.write_text(text, encoding="utf-8")
    if proc.returncode != 0 and not text:
        return text, f"exit:{proc.returncode}"
    return text, None


def run_iris(manifest: dict[str, Any], prompt: str, out_txt: Path) -> tuple[str, str | None]:
    """Queue chat.send then poll ~/.iris-light chat_messages for the assistant reply."""
    # Isolate context so prior bench turns do not bleed into grading.
    iris_invoke("chat.new_session", {}, timeout=30.0)
    before_id = iris_max_message_id()
    sent = iris_invoke("chat.send", {"text": prompt}, timeout=60.0)
    if not sent.get("ok"):
        out_txt.write_text(json.dumps(sent, ensure_ascii=False, indent=2), encoding="utf-8")
        return "", f"chat.send:{sent.get('error') or sent.get('status') or 'failed'}"
    deadline = time.monotonic() + float(manifest.get("iris_turn_timeout_s", 300))
    text = ""
    msg_id = 0
    stable_hits = 0
    last_len = -1
    first_seen_at: float | None = None
    # Tool turns often append after a short draft; wait for quiet period.
    while time.monotonic() < deadline:
        time.sleep(2.0)
        got = iris_assistant_after(before_id)
        if got is None:
            continue
        msg_id, text = got
        if first_seen_at is None and text.strip():
            first_seen_at = time.monotonic()
        if len(text) == last_len and text.strip():
            stable_hits += 1
            quiet_ok = first_seen_at is not None and (time.monotonic() - first_seen_at) >= 8.0
            if stable_hits >= 3 and quiet_ok:
                break
        else:
            stable_hits = 0
            last_len = len(text)
    payload = {
        "chat_send": sent,
        "before_message_id": before_id,
        "assistant_message_id": msg_id,
        "text": text,
    }
    out_txt.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if not text.strip():
        return "", "iris:no_assistant_reply"
    return text, None


def execute_case(
    *,
    run_dir: Path,
    manifest: dict[str, Any],
    arm: str,
    case: dict[str, Any],
    execute: bool,
) -> dict[str, Any]:
    case_id = case["id"]
    grade = case.get("grade") or {}
    kind = grade.get("kind")
    t0 = time.monotonic()
    raw_dir = run_dir / "raw" / arm
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_txt = raw_dir / f"{case_id}.txt"

    if kind in ("swe_placeholder", "gaia_placeholder"):
        row = {
            "arm": arm,
            "case_id": case_id,
            "phase": case["phase"],
            "axis": case.get("axis"),
            "ok": None,
            "status": "skipped",
            "elapsed_s": 0.0,
            "output_path": None,
            "error": kind,
            "model": manifest["model"],
            "graded": kind,
        }
        write_json(result_path(run_dir, arm, case_id), row)
        return row

    if not execute:
        row = {
            "arm": arm,
            "case_id": case_id,
            "phase": case["phase"],
            "axis": case.get("axis"),
            "ok": None,
            "status": "dry",
            "elapsed_s": 0.0,
            "output_path": None,
            "error": None,
            "model": manifest["model"],
            "graded": grade.get("kind"),
        }
        write_json(result_path(run_dir, arm, case_id), row)
        return row

    err: str | None = None
    text = ""
    prompt = str(case.get(f"prompt_{arm}") or case.get("prompt") or "")
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    effect_meta: dict[str, Any] | None = None
    if kind == "product_effect":
        before = snapshot_product(grade)

    if arm == "hermes":
        text, err = run_hermes(manifest, prompt, out_txt)
    else:
        text, err = run_iris(manifest, prompt, out_txt)

    if kind == "product_effect":
        after = snapshot_product(grade)
        ok, graded, effect_meta = grade_product_effect(
            grade, arm=arm, text=text, before=before, after=after
        )
        # Keep raw + effect audit trail for Iris JSON payloads.
        if arm == "iris" and out_txt.is_file():
            try:
                payload = json.loads(out_txt.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = {"text": text}
            payload["product_effect"] = {
                "before": before,
                "after": after,
                "meta": effect_meta,
            }
            out_txt.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            audit = out_txt.with_suffix(".effect.json")
            write_json(audit, {"before": before, "after": after, "meta": effect_meta, "text": text})
    else:
        ok, graded = grade_text(grade, text)

    if err:
        status = "error"
        ok = False
    elif ok is None:
        status = "manual"
    elif ok:
        status = "pass"
    else:
        status = "fail"

    row = {
        "arm": arm,
        "case_id": case_id,
        "phase": case["phase"],
        "axis": case.get("axis"),
        "ok": ok,
        "status": status,
        "elapsed_s": round(time.monotonic() - t0, 3),
        "output_path": str(out_txt),
        "error": err,
        "model": manifest["model"],
        "graded": graded,
        "finished_at": utc_now(),
        "effect": effect_meta,
    }
    write_json(result_path(run_dir, arm, case_id), row)
    return row


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", required=True, help="prepare.py output directory")
    p.add_argument("--phase", type=int, required=True, choices=[1, 2, 3, 4])
    p.add_argument("--arm", choices=["iris", "hermes", "both"], default="both")
    p.add_argument(
        "--execute",
        action="store_true",
        help="Actually call Hermes/Iris. Without this flag, dry-run only.",
    )
    p.add_argument(
        "--resume",
        action="store_true",
        help="Skip cases that already have a finished result JSON (pass/fail/manual/skipped/error).",
    )
    ns = p.parse_args()
    run_dir = Path(ns.run_dir)
    if not run_dir.is_dir():
        # allow run-id shorthand
        alt = WORK_ROOT / ns.run_dir
        run_dir = alt if alt.is_dir() else run_dir
    manifest = load_manifest(run_dir)
    cases = load_cases(ns.phase)
    arms = ["hermes", "iris"] if ns.arm == "both" else [ns.arm]
    summary: list[dict[str, Any]] = []
    # Sequential arms: hermes first then iris (fair GPU / Ollama).
    for arm in arms:
        for case in cases:
            existing = result_path(run_dir, arm, case["id"])
            if ns.resume and existing.is_file():
                prev = json.loads(existing.read_text(encoding="utf-8"))
                if prev.get("finished_at") and prev.get("status") in (
                    "pass",
                    "fail",
                    "manual",
                    "skipped",
                    "error",
                ):
                    summary.append(prev)
                    print(
                        json.dumps(
                            {
                                "case": case["id"],
                                "arm": arm,
                                "status": prev.get("status"),
                                "resumed": True,
                            },
                            ensure_ascii=False,
                        )
                    )
                    continue
            row = execute_case(
                run_dir=run_dir,
                manifest=manifest,
                arm=arm,
                case=case,
                execute=bool(ns.execute),
            )
            summary.append(row)
            print(json.dumps({"case": row["case_id"], "arm": arm, "status": row["status"]}, ensure_ascii=False))
    write_json(
        run_dir / f"phase{ns.phase}_{'execute' if ns.execute else 'dry'}_summary.json",
        {"phase": ns.phase, "execute": bool(ns.execute), "rows": summary},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
