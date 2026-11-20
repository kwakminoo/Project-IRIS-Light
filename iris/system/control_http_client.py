"""Control Surface HTTP helpers (ex-MCP stdio). Speak path is SpeakTools."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

def _state_dir() -> Path:
    return Path.home() / ".iris-light"


def _load_endpoint() -> tuple[str, str]:
    host = (os.environ.get("IRIS_CONTROL_HOST") or "").strip()
    port = (os.environ.get("IRIS_CONTROL_PORT") or "").strip()
    token = (os.environ.get("IRIS_CONTROL_TOKEN") or "").strip()
    base = (os.environ.get("IRIS_CONTROL_URL") or "").strip().rstrip("/")

    if not host:
        hp = _state_dir() / "control_host"
        if hp.is_file():
            host = hp.read_text(encoding="utf-8").strip()
    if not port:
        pp = _state_dir() / "control_port"
        if pp.is_file():
            port = pp.read_text(encoding="utf-8").strip()
    if not token:
        tp = _state_dir() / "control_token"
        if tp.is_file():
            token = tp.read_text(encoding="utf-8").strip()

    if not base:
        host = host or "127.0.0.1"
        port = port or "8765"
        base = f"http://{host}:{port}"
    return base, token


def _http(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    import time

    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    last_base = ""
    last_reason: object = ""
    # Iris 재기동·gateway 재부착 직후 짧은 공백 — 즉시 실패하지 말고 재시도
    for attempt in range(3):
        base, token = _load_endpoint()
        last_base = base
        if not token:
            return {
                "ok": False,
                "action": "http",
                "result": {},
                "error": "IRIS_CONTROL_TOKEN missing (set env or ~/.iris-light/control_token). Is Iris running?",
                "transport": True,
            }
        url = f"{base}{path}"
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            # email.list_messages IMAP 등 긴 액션 — 기본 60s면 refresh 시 끊길 수 있음
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read().decode("utf-8")
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return {
                    "ok": False,
                    "action": "http",
                    "result": {},
                    "error": "invalid JSON from Iris",
                    "transport": True,
                }
            return parsed if isinstance(parsed, dict) else {
                "ok": False,
                "error": "bad response",
                "transport": True,
            }
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read().decode("utf-8")
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
            return {
                "ok": False,
                "action": "http",
                "result": {},
                "error": f"HTTP {exc.code}: Iris control rejected request",
                "transport": True,
            }
        except urllib.error.URLError as exc:
            last_reason = exc.reason
            time.sleep(0.35 * (attempt + 1))
            continue
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "action": "http",
                "result": {},
                "error": f"Iris control error: {exc}",
                "transport": True,
            }
    return {
        "ok": False,
        "action": "http",
        "result": {},
        "error": (
            f"Iris control unreachable at {last_base} ({last_reason}). "
            "Start Iris Light first."
        ),
        "transport": True,
    }

def _tool_result(payload: dict[str, Any]) -> dict[str, Any]:
    # Hermes는 isError 응답을 연결 실패로 센다 (mcp_tool.py: "error" in parsed → breaker).
    # 도구가 답한 실행 오류는 isError를 켜지 않는다. ok는 그대로 false.
    text = json.dumps(payload, ensure_ascii=True, indent=2)
    failed = not bool(payload.get("ok", True)) and bool(payload.get("error"))
    transport = bool(payload.get("transport"))
    return {
        "content": [{"type": "text", "text": text}],
        "isError": bool(failed and transport),
    }

