#!/usr/bin/env python3
"""Build final Iris vs Hermes comparison table from ArmResult JSON files."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib import WORK_ROOT, write_json


def load_results(run_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    root = run_dir / "results"
    if not root.is_dir():
        return rows
    for path in sorted(root.rglob("*.json")):
        rows.append(json.loads(path.read_text(encoding="utf-8")))
    return rows


def score_bucket(rows: list[dict[str, Any]], arm: str, phase: int | None = None) -> dict[str, Any]:
    subset = [r for r in rows if r.get("arm") == arm and (phase is None or r.get("phase") == phase)]
    scored = [r for r in subset if r.get("status") in ("pass", "fail")]
    passed = sum(1 for r in scored if r.get("status") == "pass")
    failed = sum(1 for r in scored if r.get("status") == "fail")
    manual = sum(1 for r in subset if r.get("status") == "manual")
    skipped = sum(1 for r in subset if r.get("status") == "skipped")
    dry = sum(1 for r in subset if r.get("status") == "dry")
    errors = sum(1 for r in subset if r.get("status") == "error")
    return {
        "n": len(subset),
        "scored": len(scored),
        "pass": passed,
        "fail": failed,
        "manual": manual,
        "skipped": skipped,
        "dry": dry,
        "error": errors,
        "pass_rate": (passed / len(scored)) if scored else None,
    }


def render_md(manifest: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Iris vs Hermes capability bench",
        "",
        f"- model: `{manifest.get('model')}`",
        f"- base_url: `{manifest.get('base_url')}`",
        f"- run_dir: `{manifest.get('work_dir', '')}`",
        "",
        "| Phase | Hermes pass/scored | Iris pass/scored | Δ (Iris−Hermes) | manual/skip/error |",
        "|---|---|---|---|---|",
    ]
    for phase in (1, 2, 3, 4):
        h = score_bucket(rows, "hermes", phase)
        i = score_bucket(rows, "iris", phase)
        hp, hs = h["pass"], h["scored"]
        ip, is_ = i["pass"], i["scored"]
        if hs and is_ and h["pass_rate"] is not None and i["pass_rate"] is not None:
            delta = f"{(i['pass_rate'] - h['pass_rate']) * 100:.1f}pp"
        else:
            delta = "n/a"
        misc = f"H m{h['manual']}/s{h['skipped']}/e{h['error']} · I m{i['manual']}/s{i['skipped']}/e{i['error']}"
        lines.append(f"| {phase} | {hp}/{hs} | {ip}/{is_} | {delta} | {misc} |")
    h = score_bucket(rows, "hermes")
    i = score_bucket(rows, "iris")
    lines.extend(
        [
            "",
            "## Overall",
            "",
            f"- Hermes: {h['pass']}/{h['scored']} scored pass (manual={h['manual']}, skip={h['skipped']}, dry={h['dry']}, error={h['error']})",
            f"- Iris: {i['pass']}/{i['scored']} scored pass (manual={i['manual']}, skip={i['skipped']}, dry={i['dry']}, error={i['error']})",
            "",
            "Manual rows need human OK/FAIL in results JSON before treating rates as final.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", required=True)
    ns = p.parse_args()
    run_dir = Path(ns.run_dir)
    if not run_dir.is_dir():
        alt = WORK_ROOT / ns.run_dir
        run_dir = alt if alt.is_dir() else run_dir
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    rows = load_results(run_dir)
    by_phase: dict[str, Any] = {}
    for phase in (1, 2, 3, 4):
        by_phase[str(phase)] = {
            "hermes": score_bucket(rows, "hermes", phase),
            "iris": score_bucket(rows, "iris", phase),
        }
    report = {
        "model": manifest.get("model"),
        "base_url": manifest.get("base_url"),
        "phases": by_phase,
        "overall": {"hermes": score_bucket(rows, "hermes"), "iris": score_bucket(rows, "iris")},
        "rows": rows,
    }
    md = render_md(manifest, rows)
    write_json(run_dir / "report.json", report)
    (run_dir / "report.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
