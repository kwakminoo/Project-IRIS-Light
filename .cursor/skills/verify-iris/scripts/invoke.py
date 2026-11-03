"""POST /v1/invoke against the live Iris control surface (~/.iris-light)."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

CONTROL_DIR = Path.home() / ".iris-light"


def invoke(action: str, args: dict | None = None, *, timeout: float = 180.0) -> dict:
    port = (CONTROL_DIR / "control_port").read_text(encoding="utf-8").strip()
    token = (CONTROL_DIR / "control_token").read_text(encoding="utf-8").strip()
    data = json.dumps({"action": action, "args": args or {}}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/invoke",
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
    p = argparse.ArgumentParser(description="Iris control /v1/invoke")
    p.add_argument("action")
    p.add_argument("--args", default="{}", help="JSON object for args")
    p.add_argument("--timeout", type=float, default=180.0)
    ns = p.parse_args()
    try:
        args = json.loads(ns.args)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": f"bad --args: {exc}"}, ensure_ascii=False))
        return 2
    if not isinstance(args, dict):
        print(json.dumps({"ok": False, "error": "--args must be a JSON object"}, ensure_ascii=False))
        return 2
    if not (CONTROL_DIR / "control_port").is_file():
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "no live Iris control_port; start Iris or use a headless feature",
                },
                ensure_ascii=False,
            )
        )
        return 1
    out = invoke(ns.action, args, timeout=ns.timeout)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
