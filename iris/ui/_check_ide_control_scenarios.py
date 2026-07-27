"""IDE / project 시나리오 10개 — 기대 vs 실제 리포트.

제어면 HTTP + Hermes MCP/스킬 배선 검증.
NL→Hermes LLM 경로는 인프라가 준비됐는지까지 확인 (실제 LLM 응답은 수동).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".iris_light_test_tmp" / "ide_scenario_report.json"


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
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return {"http": resp.status, **json.loads(resp.read().decode("utf-8"))}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return {"http": exc.code, "ok": False, **parsed}
    except Exception as exc:  # noqa: BLE001
        return {"http": 0, "ok": False, "error": str(exc)}


def invoke(action: str, args: dict | None = None) -> dict:
    return http("POST", "/v1/invoke", {"action": action, "args": args or {}})


def state() -> dict:
    r = http("GET", "/v1/state")
    return r.get("result") if isinstance(r.get("result"), dict) else {}


def mcp_call_state() -> dict:
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
        return json.loads(proc.stdout.read(n).decode("utf-8"))

    try:
        send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "ide-scenarios", "version": "0"},
                },
            }
        )
        recv()
        send(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "iris_get_state", "arguments": {}},
            }
        )
        r2 = recv()
        return {"call": r2}
    finally:
        try:
            proc.terminate()
        except Exception:
            pass


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from iris.system.hermes_iris_control_sync import sync_iris_control, verify_install

    sync = sync_iris_control()
    verified = verify_install()

    scenarios: list[dict] = []

    def add(
        sid: int,
        name: str,
        expect: str,
        actual: str,
        passed: bool,
        *,
        fix: str = "",
        detail: dict | None = None,
    ) -> None:
        scenarios.append(
            {
                "id": sid,
                "name": name,
                "expect": expect,
                "actual": actual,
                "pass": passed,
                "fix_if_fail": fix if not passed else "",
                "detail": detail or {},
            }
        )

    # 1 sync MCP
    add(
        1,
        "Hermes config에 iris-control MCP 자동 설치",
        "mcp_servers.iris-control 존재·일치",
        f"mcp_installed={verified.mcp_installed} changed={sync.mcp_changed}",
        verified.mcp_installed,
        fix="iris/system/hermes_iris_control_sync.py ensure_mcp_in_config / Hermes config 쓰기 권한",
        detail={"sync": sync.messages, "errors": sync.errors},
    )

    # 2 skills
    add(
        2,
        "iris-work-* 스킬 3개 Hermes skills에 설치",
        "iris-work-start/end/session-status SKILL.md 존재",
        f"ok={verified.skills_ok} missing={verified.skills_missing}",
        len(verified.skills_ok) == 3 and not verified.skills_missing,
        fix="ensure_skills_installed 경로·복사 권한 확인",
    )

    # 3 persist marker
    state_file = Path.home() / ".iris-light" / "hermes_iris_control_sync.json"
    add(
        3,
        "동기화 상태가 Iris 재시작 후에도 남는 파일로 기록",
        "~/.iris-light/hermes_iris_control_sync.json 존재",
        f"exists={state_file.is_file()}",
        state_file.is_file(),
        fix="sync_iris_control 끝의 state write",
    )

    # 4 control ping
    ping = http("GET", "/v1/ping")
    add(
        4,
        "Iris Control Surface 생존 (IDE 조작 전제)",
        "GET /v1/ping ok",
        str(ping.get("ok")),
        bool(ping.get("ok")),
        fix="Iris 실행·IRIS_CONTROL_ENABLED·포트 8765",
    )

    # 5 set project root to Iris Light
    r = invoke("ide.set_project_root", {"path": str(ROOT)})
    st = state()
    add(
        5,
        "프로젝트 루트를 Iris Light로 설정",
        f"project_root == {ROOT}",
        f"ok={r.get('ok')} root={st.get('project_root')}",
        bool(r.get("ok")) and Path(str(st.get("project_root") or "")) == ROOT,
        fix="ide.set_project_root 핸들러 / 경로 존재 검증",
        detail={"invoke": r},
    )

    # 6 enter companion (= IDE icon)
    r = invoke("ide.enter_companion", {})
    st = state()
    add(
        6,
        "IDE Companion 켜기 (아이콘과 동일)",
        "ui_mode=ide_companion, ide 창 attach",
        f"ok={r.get('ok')} ui_mode={st.get('ui_mode')} hwnd={st.get('ide_attached')}",
        st.get("ui_mode") == "ide_companion" and bool(r.get("ok")),
        fix="ide_launcher/tiler / preferred_ide 설치 / enter_companion 에러 로그",
        detail={"invoke": r},
    )

    # 7 exit companion
    r = invoke("ide.exit_companion", {})
    st = state()
    add(
        7,
        "IDE Companion 끄기 (IDE 창 유지)",
        "ui_mode=normal",
        f"ok={r.get('ok')} ui_mode={st.get('ui_mode')}",
        st.get("ui_mode") == "normal" and bool(r.get("ok")),
        fix="ide.exit_companion / _apply_ide_companion_layout",
    )

    # 8 open other project folder then companion
    other = Path.home() / "Desktop"
    if not other.is_dir():
        other = Path.home()
    r1 = invoke("ide.set_project_root", {"path": str(other)})
    r2 = invoke("ide.enter_companion", {})
    st = state()
    add(
        8,
        "다른 폴더를 project_root로 열고 Companion",
        f"project_root={other} + ui_mode=ide_companion",
        f"root={st.get('project_root')} ui={st.get('ui_mode')} r1={r1.get('ok')} r2={r2.get('ok')}",
        Path(str(st.get("project_root") or "")) == other.resolve()
        and st.get("ui_mode") == "ide_companion",
        fix="enter_companion이 새 project_root로 IDE를 다시 여는지는 launch_ide 인자 확인 — "
        "이미 IDE가 떠 있으면 폴더만 안 바뀔 수 있음(개선: relaunch/open folder 액션)",
        detail={"r1": r1, "r2": r2},
    )

    # 9 create new project dir + set root + companion
    new_proj = Path(tempfile.mkdtemp(prefix="iris_scenario_proj_"))
    (new_proj / "README.md").write_text("# scenario project\n", encoding="utf-8")
    (new_proj / "main.py").write_text("print('hello iris')\n", encoding="utf-8")
    r1 = invoke("ide.set_project_root", {"path": str(new_proj)})
    r2 = invoke("ide.enter_companion", {})
    st = state()
    add(
        9,
        "새 프로젝트 폴더 생성 후 IDE Companion으로 열기",
        "새 경로가 project_root이고 companion 활성",
        f"root={st.get('project_root')} ui={st.get('ui_mode')}",
        Path(str(st.get("project_root") or "")) == new_proj.resolve()
        and st.get("ui_mode") == "ide_companion",
        fix="새 폴더 open: IDE 이미 attach면 창만 타일 — "
        "ide.open_folder / relaunch 액션 또는 CLI로 폴더 전달 필요. "
        "코딩(파일 작성)은 Hermes terminal/patch 또는 Iris 채팅이 담당(Companion은 레이아웃)",
        detail={"project": str(new_proj), "r1": r1, "r2": r2},
    )

    # 10 MCP stdio invoke path (what Hermes uses)
    try:
        mcp = mcp_call_state()
        text = ""
        node = mcp.get("call") or {}
        content = ((node.get("result") or {}).get("content") or [{}])
        if content and isinstance(content[0], dict):
            text = str(content[0].get("text") or "")
        parsed_ok = False
        try:
            body = json.loads(text)
            parsed_ok = bool(body.get("ok"))
        except Exception:
            parsed_ok = "\"ok\": true" in text or '"ok":true' in text.replace(" ", "")
        add(
            10,
            "MCP stdio → iris_get_state (Hermes가 쓸 경로)",
            "stdio MCP가 Control Surface get_state 성공",
            f"parsed_ok={parsed_ok} preview={text[:120]}",
            parsed_ok,
            fix="iris.mcp.iris_control_stdio / PYTHONPATH·cwd / control_token",
            detail={"mcp_keys": list(mcp.keys())},
        )
    except Exception as exc:  # noqa: BLE001
        add(
            10,
            "MCP stdio → iris_get_state (Hermes가 쓸 경로)",
            "stdio MCP가 Control Surface get_state 성공",
            f"error={exc}",
            False,
            fix="stdio 브리지 예외 수정",
        )

    # restore project root to Iris Light for user convenience
    invoke("ide.exit_companion", {})
    invoke("ide.set_project_root", {"path": str(ROOT)})

    report = {
        "sync_ok": sync.ok,
        "verified_mcp": verified.mcp_installed,
        "verified_skills": verified.skills_ok,
        "passed": sum(1 for s in scenarios if s["pass"]),
        "total": len(scenarios),
        "scenarios": scenarios,
        "notes": [
            "시나리오 1–3·10: Hermes 배선/인프라",
            "시나리오 4–9: Iris Control Surface (= IDE 아이콘과 동일 핸들러)",
            "채팅 NL '코딩해줘'의 LLM 품질은 별도 — 인프라만 통과해도 모델이 terminal로 샐 수 있음 → MEMORY nudge + 스킬로 완화",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "wrote": str(OUT),
                "passed": report["passed"],
                "total": report["total"],
                "fails": [
                    {"id": s["id"], "name": s["name"], "actual": s["actual"], "fix": s["fix_if_fail"]}
                    for s in scenarios
                    if not s["pass"]
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
