"""Call the live IRIS control surface. Not imported by IRIS."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

HOME = Path.home() / ".iris-light"


def _endpoint() -> tuple[str, str]:
    token = (HOME / "control_token").read_text(encoding="utf-8").strip()
    port = (HOME / "control_port").read_text(encoding="utf-8").strip()
    return f"http://127.0.0.1:{port}", token


def call(method: str, path: str, body: dict | None = None) -> dict:
    base, token = _endpoint()
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return {"http": resp.status, **json.loads(resp.read().decode("utf-8"))}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"raw": raw[:400]}
        return {"http": exc.code, "ok": False, **parsed}
    except Exception as exc:
        return {"http": 0, "ok": False, "error": str(exc)}


def main() -> int:
    kind = sys.argv[1] if len(sys.argv) > 1 else "state"
    if kind == "state":
        print(json.dumps(call("GET", "/v1/state"), ensure_ascii=False, indent=2)[:4000])
        return 0
    action = kind
    args = {}
    if len(sys.argv) > 2:
        args = json.loads(sys.argv[2])
    print(json.dumps(call("POST", "/v1/invoke", {"action": action, "args": args}), ensure_ascii=False, indent=2)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
