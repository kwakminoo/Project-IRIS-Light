"""시나리오 10개 — 폴더 전환·유사 매칭·구구단 스캐폴드."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".iris_light_test_tmp" / "ide_scenario_v2_report.json"
CUSOR = Path.home() / "Desktop" / "Cusor-Project"


def _endpoint() -> tuple[str, str]:
    d = Path.home() / ".iris-light"
    return (
        f"http://127.0.0.1:{(d / 'control_port').read_text(encoding='utf-8').strip()}",
        (d / "control_token").read_text(encoding="utf-8").strip(),
    )


def http(method: str, path: str, body: dict | None = None) -> dict:
    base, token = _endpoint()
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
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


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from iris.system.hermes_iris_control_sync import sync_iris_control
    from iris.system.project_ops import find_similar_projects

    sync_iris_control()  # skills update

    scenarios: list[dict] = []

    def add(sid: int, name: str, expect: str, actual: str, passed: bool, fix: str = "", detail=None):
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

    # 1 catalog has new actions
    cat = http("GET", "/v1/catalog")
    names = [a.get("name") for a in ((cat.get("result") or {}).get("actions") or [])]
    need = {
        "ide.open_folder",
        "project.find_similar",
        "project.open_similar",
        "project.create_scaffold",
        "project.write_file",
    }
    missing = sorted(need - set(names))
    add(
        1,
        "신규 액션 카탈로그 등록",
        f"{sorted(need)} 모두 존재",
        f"missing={missing} count={len(names)}",
        not missing,
        fix="Iris 재시작 후 control_bindings 로드 / 카탈로그 등록 확인",
        detail={"names_sample": names[-10:]},
    )

    # 2 fuzzy find AI guitar tab
    hits = find_similar_projects("ai guitar tab")
    best = hits[0] if hits else None
    add(
        2,
        "유사 폴더 검색: ai guitar tab → AI-Guitar-Tab-main",
        "best.name == AI-Guitar-Tab-main (또는 guitar+tab 포함)",
        str(best),
        bool(best) and "guitar" in best["name"].lower() and "tab" in best["name"].lower(),
        fix="project_ops.find_similar_projects / Cusor-Project 부모 경로",
    )

    # 3 open similar via control surface
    r = invoke("project.open_similar", {"query": "AI guitar tab 작업"})
    st = state()
    add(
        3,
        "project.open_similar 로 Companion + 유사 폴더 열기",
        "ok + ui_mode=ide_companion + project_root에 Guitar-Tab",
        f"ok={r.get('ok')} ui={st.get('ui_mode')} root={st.get('project_root')}",
        bool(r.get("ok"))
        and st.get("ui_mode") == "ide_companion"
        and "guitar" in str(st.get("project_root") or "").lower(),
        fix="MainWindow._open_ide_folder / open_folder_in_ide CLI / Iris 재시작",
        detail={"invoke": r},
    )

    time.sleep(1.0)

    # 4 switch to Iris Light folder while IDE already open
    r = invoke("ide.open_folder", {"path": str(ROOT), "new_window": True})
    st = state()
    add(
        4,
        "이미 IDE가 열린 상태에서 다른 폴더(Iris Light)로 전환",
        "project_root=Iris Light + companion",
        f"ok={r.get('ok')} root={st.get('project_root')} ui={st.get('ui_mode')}",
        bool(r.get("ok"))
        and Path(str(st.get("project_root") or "")) == ROOT
        and st.get("ui_mode") == "ide_companion",
        fix="ide.open_folder new_window=True / Cursor CLI --new-window",
        detail={"invoke": r},
    )

    time.sleep(1.0)

    # 5 switch to Desktop Cusor-Project parent sibling Writing-Practice
    writing = CUSOR / "Writing-Practice-main"
    r = invoke("ide.open_folder", {"path": str(writing), "new_window": True})
    st = state()
    add(
        5,
        "Companion 유지하며 Writing-Practice-main 으로 폴더 교체",
        "project_root=Writing-Practice-main + companion",
        f"ok={r.get('ok')} root={st.get('project_root')} ui={st.get('ui_mode')}",
        bool(r.get("ok"))
        and "Writing-Practice" in str(st.get("project_root") or "")
        and st.get("ui_mode") == "ide_companion",
        fix="open_folder_in_ide / 창 탐색 타임아웃",
        detail={"invoke": r, "exists": writing.is_dir()},
    )

    # 6 create gugudan test project + open
    r = invoke(
        "project.create_scaffold",
        {
            "parent": str(CUSOR),
            "name": "iris-gugudan-test",
            "template": "gugudan",
            "open": True,
            "new_window": True,
        },
    )
    st = state()
    created = ((r.get("result") or {}).get("created") or {})
    gugudan_path = Path(str(created.get("path") or ""))
    code_ok = (gugudan_path / "gugudan.py").is_file() if gugudan_path else False
    add(
        6,
        "테스트폴더 생성(구구단 템플릿) + IDE에서 열기",
        "iris-gugudan-test 생성, gugudan.py 존재, companion",
        f"ok={r.get('ok')} path={created.get('path')} code={code_ok} ui={st.get('ui_mode')}",
        bool(r.get("ok")) and code_ok and st.get("ui_mode") == "ide_companion",
        fix="project.create_scaffold / template gugudan",
        detail={"invoke": r},
    )

    # 7 verify gugudan.py content has input + 구구단 loop
    text = ""
    if code_ok:
        text = (gugudan_path / "gugudan.py").read_text(encoding="utf-8")
    add(
        7,
        "구구단 코드: 숫자 입력 받아 단 출력",
        "input( + for i in range(1,10) + 곱셈 출력",
        f"has_input={'input(' in text} has_loop={'range(1, 10)' in text or 'range(1,10)' in text}",
        "input(" in text and ("range(1, 10)" in text or "range(1,10)" in text),
        fix="project_ops._GUGUDAN_PY 템플릿",
    )

    # 8 write_file extra helper
    if gugudan_path.is_dir():
        r = invoke(
            "project.write_file",
            {
                "project_root": str(gugudan_path),
                "rel_path": "notes.txt",
                "content": "gugudan scenario ok\n",
            },
        )
        notes_ok = (gugudan_path / "notes.txt").is_file()
    else:
        r = {"ok": False, "error": "no project"}
        notes_ok = False
    add(
        8,
        "project.write_file 로 프로젝트에 메모 추가",
        "notes.txt 생성",
        f"ok={r.get('ok')} notes={notes_ok}",
        bool(r.get("ok")) and notes_ok,
        fix="project.write_file 경로 escape 검증",
        detail={"invoke": r},
    )

    # 9 find_similar via invoke API
    r = invoke("project.find_similar", {"query": "iris light", "limit": 5})
    matches = (r.get("result") or {}).get("matches") or []
    best_name = (matches[0].get("name") if matches else "") or ""
    add(
        9,
        "project.find_similar('iris light')",
        "상위 매치에 Project-IRIS-Light-main",
        f"ok={r.get('ok')} best={best_name}",
        bool(r.get("ok")) and "iris" in best_name.lower() and "light" in best_name.lower(),
        fix="유사도 토큰/보너스 조정",
        detail={"matches": matches[:3]},
    )

    # 10 exit companion restore
    r = invoke("ide.exit_companion", {})
    st = state()
    # restore project root to iris light for user
    invoke("ide.set_project_root", {"path": str(ROOT)})
    add(
        10,
        "Companion 종료 후 일반 레이아웃",
        "ui_mode=normal",
        f"ok={r.get('ok')} ui={st.get('ui_mode')}",
        st.get("ui_mode") == "normal" and bool(r.get("ok")),
        fix="ide.exit_companion",
    )

    report = {
        "passed": sum(1 for s in scenarios if s["pass"]),
        "total": len(scenarios),
        "scenarios": scenarios,
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
