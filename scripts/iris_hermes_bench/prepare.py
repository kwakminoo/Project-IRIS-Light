#!/usr/bin/env python3
"""Create an isolated bench run directory and gate readiness."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib import (
    TEMPLATE,
    WORK_ROOT,
    expand_path,
    iris_invoke,
    load_defaults,
    ollama_has_model,
    utc_now,
    write_json,
)


def build_run_dir(run_id: str | None) -> Path:
    rid = run_id or utc_now()
    run_dir = WORK_ROOT / rid
    hermes_home = run_dir / "hermes_home"
    results = run_dir / "results"
    hermes_home.mkdir(parents=True, exist_ok=True)
    results.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(TEMPLATE, hermes_home / "config.yaml")
    defaults = load_defaults()
    model = defaults["model"]
    # Keep template model in sync with defaults.
    cfg = (hermes_home / "config.yaml").read_text(encoding="utf-8")
    cfg = cfg.replace("gpt-oss:120b-cloud", model)
    (hermes_home / "config.yaml").write_text(cfg, encoding="utf-8")
    manifest = {
        "run_id": rid,
        "created_at": utc_now(),
        "model": model,
        "base_url": defaults["base_url"],
        "api_key": defaults.get("api_key", "ollama"),
        "provider": defaults.get("provider", "custom"),
        "hermes_bin": str(expand_path(defaults["hermes_bin"])),
        "hermes_home": str(hermes_home),
        "results_dir": str(results),
        "max_turns": defaults.get("max_turns", 12),
        "iris_turn_timeout_s": defaults.get("iris_turn_timeout_s", 300),
        "work_dir": str(run_dir),
    }
    write_json(run_dir / "manifest.json", manifest)
    return run_dir


def check_ready(manifest: dict) -> dict:
    checks: dict = {}
    hermes_bin = Path(manifest["hermes_bin"])
    checks["hermes_bin"] = {"ok": hermes_bin.is_file(), "path": str(hermes_bin)}
    model_ok, model_detail = ollama_has_model(manifest["model"])
    checks["model"] = {"ok": model_ok, "model": manifest["model"], "detail": model_detail}
    ping = iris_invoke("ping", {})
    checks["iris_control"] = {
        "ok": bool(ping.get("ok")) and ping.get("status") == "success",
        "body": {k: ping.get(k) for k in ("ok", "status", "error", "http")},
    }
    hermes_cfg = Path(manifest["hermes_home"]) / "config.yaml"
    text = hermes_cfg.read_text(encoding="utf-8") if hermes_cfg.is_file() else ""
    has_iris_mcp = ("iris-control:" in text) or ("iris_control:" in text)
    checks["hermes_isolated_config"] = {
        "ok": hermes_cfg.is_file() and not has_iris_mcp and "mcp_servers: {}" in text.replace("\r\n", "\n"),
        "path": str(hermes_cfg),
    }
    ready = all(c.get("ok") for c in checks.values())
    # Iris live is recommended for Iris arm but Hermes-only dry prepare can warn.
    if not checks["iris_control"]["ok"]:
        ready = False
    return {"ready": ready, "checks": checks}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", default="")
    p.add_argument("--check-only", action="store_true")
    ns = p.parse_args()
    if ns.check_only and ns.run_id:
        run_dir = WORK_ROOT / ns.run_id
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    else:
        run_dir = build_run_dir(ns.run_id or None)
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    report = check_ready(manifest)
    report["run_dir"] = str(run_dir)
    report["manifest"] = {
        "model": manifest["model"],
        "hermes_bin": manifest["hermes_bin"],
        "hermes_home": manifest["hermes_home"],
    }
    write_json(run_dir / "prepare_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
