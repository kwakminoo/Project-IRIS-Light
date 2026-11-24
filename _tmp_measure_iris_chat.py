"""Measure Iris chat.send round-trip via control HTTP + DB/agent.log."""
from __future__ import annotations

import json
import sqlite3
import time
import urllib.request
from pathlib import Path

CONTROL = Path.home() / ".iris-light"
DB = CONTROL / "iris_light.db"
AGENT_LOG = CONTROL / "agent" / "logs" / "agent.log"
OUT = Path(".iris_light_test_tmp") / "verify-iris" / "live-model-measure"
OUT.mkdir(parents=True, exist_ok=True)


def invoke(action: str, args: dict | None = None, timeout: float = 30.0) -> dict:
    port = (CONTROL / "control_port").read_text(encoding="utf-8").strip()
    token = (CONTROL / "control_token").read_text(encoding="utf-8").strip()
    data = json.dumps({"action": action, "args": args or {}}, ensure_ascii=False).encode(
        "utf-8"
    )
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/invoke",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def latest_user_id() -> int:
    con = sqlite3.connect(str(DB))
    row = con.execute(
        "select id from chat_messages where role='user' order by id desc limit 1"
    ).fetchone()
    con.close()
    return int(row[0]) if row else 0


def assistant_after(user_id: int) -> tuple[str, str] | None:
    con = sqlite3.connect(str(DB))
    row = con.execute(
        "select content, created_at from chat_messages "
        "where id>? and role='assistant' order by id asc limit 1",
        (user_id,),
    ).fetchone()
    con.close()
    if not row:
        return None
    return str(row[0] or ""), str(row[1] or "")


def agent_tail(n: int = 40) -> str:
    if not AGENT_LOG.is_file():
        return ""
    lines = AGENT_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-n:])


def measure(label: str, text: str, wait_sec: float = 120.0) -> dict:
    state = invoke("get_state")
    model = (state.get("result") or {}).get("model")
    before_uid = latest_user_id()
    t0 = time.perf_counter()
    send = invoke("chat.send", {"text": text})
    t_queued = time.perf_counter() - t0
    deadline = time.perf_counter() + wait_sec
    reply = None
    while time.perf_counter() < deadline:
        got = assistant_after(before_uid)
        if got is not None:
            reply = got
            break
        # also detect if user row appeared then failed without assistant
        time.sleep(0.5)
    elapsed = time.perf_counter() - t0
    after_uid = latest_user_id()
    result = {
        "label": label,
        "model_at_send": model,
        "text": text,
        "send_ok": bool(send.get("ok")),
        "queued_sec": round(t_queued, 3),
        "elapsed_sec": round(elapsed, 3),
        "got_assistant": reply is not None,
        "assistant_preview": (reply[0][:240] if reply else ""),
        "assistant_at": (reply[1] if reply else ""),
        "user_id_before": before_uid,
        "user_id_after": after_uid,
        "hermes_enabled": (state.get("result") or {}).get("hermes_enabled"),
        "agent_tail": agent_tail(25),
    }
    path = OUT / f"{label}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "agent_tail"}, ensure_ascii=False))
    return result


if __name__ == "__main__":
    import sys

    label = sys.argv[1] if len(sys.argv) > 1 else "run"
    text = sys.argv[2] if len(sys.argv) > 2 else "안녕"
    wait = float(sys.argv[3]) if len(sys.argv) > 3 else 120.0
    measure(label, text, wait)
