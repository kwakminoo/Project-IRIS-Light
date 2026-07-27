"""10 scenario smoke tests for Iris Control Surface (+ MCP bridge reachability)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".iris_light_test_tmp" / "control_scenario_report.json"


def _endpoint() -> tuple[str, str]:
    d = Path.home() / ".iris-light"
    token = (d / "control_token").read_text(encoding="utf-8").strip()
    port = (d / "control_port").read_text(encoding="utf-8").strip()
    return f"http://127.0.0.1:{port}", token


def http(method: str, path: str, body: dict | None = None) -> dict:
    base, token = _endpoint()
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return {"http": resp.status, **json.loads(resp.read().decode("utf-8"))}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return {"http": exc.code, "ok": False, "error": f"HTTP {exc.code}", **parsed}
    except Exception as exc:  # noqa: BLE001
        return {"http": 0, "ok": False, "error": str(exc)}


def check_hermes_wiring() -> dict:
    cfg = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "config.yaml"
    text = cfg.read_text(encoding="utf-8", errors="replace") if cfg.is_file() else ""
    skills_root = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "skills"
    installed = []
    if skills_root.is_dir():
        installed = [
            str(p.relative_to(skills_root))
            for p in skills_root.rglob("SKILL.md")
            if "iris-control" in str(p).replace("\\", "/")
            or "iris-work" in str(p).replace("\\", "/")
        ]
    repo_skills = list(
        (ROOT / "integrations" / "hermes-skills" / "iris-control").rglob("SKILL.md")
    )
    return {
        "config_exists": cfg.is_file(),
        "mcp_servers_in_config": "mcp_servers" in text,
        "iris_control_in_config": "iris-control" in text or "iris_control" in text,
        "iris_control_skills_installed": installed,
        "iris_control_skills_in_repo": [str(p.name) for p in [x.parent for x in repo_skills]],
    }


def mcp_stdio_tools_list() -> dict:
    """Minimal initialize + tools/list against stdio bridge."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.Popen(
        [sys.executable, "-m", "iris.mcp.iris_control_stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(ROOT),
        env=env,
    )
    assert proc.stdin and proc.stdout

    def send(msg: dict) -> None:
        raw = json.dumps(msg).encode("utf-8")
        proc.stdin.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw)
        proc.stdin.flush()

    def recv() -> dict | None:
        headers: dict[str, str] = {}
        while True:
            line = proc.stdout.readline()
            if not line:
                return None
            if line in (b"\r\n", b"\n"):
                break
            text = line.decode("utf-8", errors="replace").strip()
            if ":" in text:
                k, v = text.split(":", 1)
                headers[k.strip().lower()] = v.strip()
        n = int(headers.get("content-length") or "0")
        body = proc.stdout.read(n)
        return json.loads(body.decode("utf-8"))

    try:
        send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "scenario-test", "version": "0"},
                },
            }
        )
        init = recv()
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools = recv()
        send(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "iris_get_state", "arguments": {}},
            }
        )
        state_call = recv()
        return {
            "ok": True,
            "initialize": bool(init and "result" in init),
            "tools": [t.get("name") for t in ((tools or {}).get("result") or {}).get("tools") or []],
            "state_call_preview": str(state_call)[:400],
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    finally:
        proc.kill()


def main() -> int:
    wiring = check_hermes_wiring()
    scenarios = []

    # S1 ping
    r = http("GET", "/v1/ping")
    scenarios.append({"id": 1, "name": "ping / health", "expect": "Iris alive", "result": r})

    # S2 get_state
    r = http("GET", "/v1/state")
    scenarios.append({"id": 2, "name": "get_state", "expect": "ui_mode/workspace", "result": r})

    # S3 catalog has enter_companion
    r = http("GET", "/v1/catalog")
    names = [a.get("name") for a in ((r.get("result") or {}).get("actions") or [])]
    scenarios.append(
        {
            "id": 3,
            "name": "catalog contains ide.enter_companion",
            "expect": "ide.enter_companion in catalog",
            "pass": "ide.enter_companion" in names,
            "action_count": len(names),
            "result_ok": r.get("ok"),
        }
    )

    # S4 bad token
    base, _ = _endpoint()
    req = urllib.request.Request(
        base + "/v1/state",
        headers={"Authorization": "Bearer wrong"},
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        bad = {"ok": True, "unexpected": True}
    except urllib.error.HTTPError as exc:
        bad = {"ok": False, "http": exc.code, "pass": exc.code == 401}
    scenarios.append({"id": 4, "name": "bad token -> 401", "expect": "401", "result": bad})

    # S5 set project_root to repo
    repo = str(ROOT)
    r = http("POST", "/v1/invoke", {"action": "ide.set_project_root", "args": {"path": repo}})
    scenarios.append(
        {
            "id": 5,
            "name": "ide.set_project_root -> Iris Light repo",
            "expect": "ok + saved path",
            "result": r,
        }
    )

    # S6 enter companion (UI side-effect)
    before = http("GET", "/v1/state")
    r = http("POST", "/v1/invoke", {"action": "ide.enter_companion", "args": {}})
    after = http("GET", "/v1/state")
    scenarios.append(
        {
            "id": 6,
            "name": "ide.enter_companion (same as IDE icon)",
            "expect": "ui_mode=ide_companion",
            "before_ui": (before.get("result") or {}).get("ui_mode"),
            "invoke": r,
            "after_ui": (after.get("result") or {}).get("ui_mode"),
            "pass": (after.get("result") or {}).get("ui_mode") == "ide_companion" or r.get("ok") is True,
        }
    )

    # S7 exit companion
    r = http("POST", "/v1/invoke", {"action": "ide.exit_companion", "args": {}})
    after = http("GET", "/v1/state")
    scenarios.append(
        {
            "id": 7,
            "name": "ide.exit_companion",
            "expect": "ui_mode=normal",
            "invoke": r,
            "after_ui": (after.get("result") or {}).get("ui_mode"),
        }
    )

    # S8 open email workspace
    r = http("POST", "/v1/invoke", {"action": "workspace.open_email", "args": {}})
    after = http("GET", "/v1/state")
    scenarios.append(
        {
            "id": 8,
            "name": "workspace.open_email",
            "expect": "workspace_mode=email",
            "invoke": r,
            "after_ws": (after.get("result") or {}).get("workspace_mode"),
        }
    )

    # S9 back to assistant
    r = http("POST", "/v1/invoke", {"action": "workspace.open_assistant", "args": {}})
    after = http("GET", "/v1/state")
    scenarios.append(
        {
            "id": 9,
            "name": "workspace.open_assistant",
            "expect": "workspace_mode=assistant",
            "invoke": r,
            "after_ws": (after.get("result") or {}).get("workspace_mode"),
        }
    )

    # S10 email.send without confirm denied
    r = http(
        "POST",
        "/v1/invoke",
        {"action": "email.send", "args": {"to": "x@y.z", "subject": "t", "body": "b"}},
    )
    scenarios.append(
        {
            "id": 10,
            "name": "email.send without confirm rejected",
            "expect": "ok=false confirm required",
            "result": r,
            "pass": r.get("ok") is False,
        }
    )

    mcp = mcp_stdio_tools_list()

    report = {
        "wiring": wiring,
        "diagnosis": {
            "iris_control_http": "UP" if scenarios[0]["result"].get("ok") else "DOWN",
            "hermes_mcp_registered": wiring["mcp_servers_in_config"],
            "iris_control_skills_installed": bool(wiring["iris_control_skills_installed"]),
            "likely_chat_behavior": (
                "Hermes has no iris-control MCP in config.yaml, so NL requests "
                "fall back to terminal/chat prep instead of ide.enter_companion"
            ),
        },
        "mcp_stdio_smoke": mcp,
        "scenarios": scenarios,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "diagnosis": report["diagnosis"], "mcp_tools": mcp.get("tools")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
