"""아이리스가 꺼져 있을 때 예약 루틴을 돌리는 헤드리스 실행기.

Windows 작업 스케줄러가 몇 분마다 이걸 깨운다(`iris.system.routine_wake`).
Qt 를 띄우지 않는다 — 창 없이 DB 를 보고, 필요하면 모델을 부르고, 바탕화면
알림을 띄운다.

**아이리스가 이미 떠 있으면 아무것도 하지 않는다.** 창이 자기 타이머로 훨씬 잘
처리하고(채팅·음성 전달까지 된다), 두 프로세스가 같은 루틴을 동시에 돌리면
결과가 두 번 간다.

`wake_when_closed` 를 켠 루틴만 여기서 돈다. 나머지는 창이 켜질 때까지 기다린다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

# 작업 스케줄러는 이 파일을 직접 실행한다(`-m` 이 아니라). 패키지 루트를 넣어 준다.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

EXIT_OK = 0
EXIT_SKIPPED = 0  # 할 일이 없는 것은 실패가 아니다
EXIT_ERROR = 1

_HEALTH_TIMEOUT_SEC = 2.0


def iris_is_running() -> bool:
    """컨트롤 서피스가 살아 있으면 창이 떠 있는 것이다."""
    try:
        from iris.system.control_surface import control_state_dir
    except Exception:  # noqa: BLE001
        return False
    root = control_state_dir()
    try:
        port = int((root / "control_port").read_text(encoding="utf-8").strip())
        host = (root / "control_host").read_text(encoding="utf-8").strip() or "127.0.0.1"
    except (OSError, ValueError):
        return False
    try:
        req = Request(f"http://{host}:{port}/health", method="GET")
        with urlopen(req, timeout=_HEALTH_TIMEOUT_SEC) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return bool(body.get("alive"))
    except (URLError, OSError, ValueError, json.JSONDecodeError):
        # 파일은 남았는데 프로세스가 죽은 경우 — 꺼진 것으로 본다.
        return False


def _log(message: str) -> None:
    # pythonw 로 돌면 stdout 이 없다. 작업 이력은 DB·위키에 남으므로 여기선 최선만.
    try:
        print(message, flush=True)
    except Exception:  # noqa: BLE001
        pass


def run_tick(*, force: bool = False) -> int:
    """지금 돌 차례인 `wake_when_closed` 루틴을 처리한다."""
    if not force and iris_is_running():
        _log("iris is running — leaving routines to the app")
        return EXIT_SKIPPED

    from iris.config.settings import load_settings
    from iris.infrastructure.ollama_client import OllamaClient
    from iris.knowledge.iris_state import sync_routine_note
    from iris.knowledge.iris_wiki import IrisWiki
    from iris.runtime.backend_route import is_agent_backend, route_for_routine
    from iris.runtime.model_switch import ModelSwitchService
    from iris.runtime.routine_search import format_evidence, run_search
    from iris.runtime.routine_runner import (
        build_run_messages,
        collect_due,
        format_delivery,
        notify_summary,
        record_missed,
        record_result,
    )
    from iris.storage.database import Database
    from iris.system.desktop_toast import show_toast
    from iris.system.uri_handler import routine_uri
    from iris.ui.workers.backend_call import collect_reply

    settings = load_settings()
    db = Database()
    try:
        run_now, missed = collect_due(db)
        # 창이 없을 때는 켜 둔 루틴만 건드린다. 나머지는 창이 열릴 때 판단한다.
        run_now = [d for d in run_now if d.routine.wake_when_closed]
        missed = [d for d in missed if d.routine.wake_when_closed]
        if not run_now and not missed:
            return EXIT_SKIPPED

        wiki = IrisWiki()
        history = ModelSwitchService(db, wiki=wiki)
        for due in missed:
            updated = record_missed(db, due)
            _log(f"missed: {due.routine.name}")
            if updated is not None:
                sync_routine_note(wiki, updated)

        for due in run_now:
            routine = due.routine
            route, note = route_for_routine(
                settings, db, routine, settings.ollama_model
            )
            if route is None:
                record_result(db, due, error=note or "쓸 모델이 없습니다")
                _log(f"no model for {routine.name}")
                continue
            try:
                evidence = ""
                if (routine.search or "").strip():
                    found = run_search(
                        routine.search, engine=routine.search_engine or "google_news"
                    )
                    evidence = format_evidence(found)
                    if found.error:
                        _log(f"search failed for {routine.name}: {found.error}")
                # 창이 열려 있을 때(MainWindow._routine_evidence)와 같은 근거를 준다.
                try:
                    past = history.semantic_evidence_block(
                        routine.task, OllamaClient(settings.ollama_base_url)
                    )
                except Exception as exc:  # noqa: BLE001
                    past = ""
                    _log(f"history search skipped for {routine.name}: {exc}")
                evidence = "\n\n".join(p for p in (evidence, past) if p)
                text = collect_reply(
                    route,
                    build_run_messages(
                        routine,
                        evidence=evidence,
                        tools_available=is_agent_backend(route.backend),
                    ),
                    timeout_sec=180.0,
                    think=False,
                )
            except Exception as exc:  # noqa: BLE001
                updated = record_result(db, due, error=str(exc))
                _log(f"failed: {routine.name}: {exc}")
                if routine.wants("notify"):
                    show_toast(
                        f"{routine.name} 실패",
                        str(exc)[:200],
                        launch=routine_uri(routine.id),
                    )
                if updated is not None:
                    sync_routine_note(wiki, updated)
                continue

            body = (text or "").strip()
            if note:
                body = f"{body}\n\n_{note}_" if body else note
            updated = record_result(db, due, text=body)
            _log(f"ok: {routine.name}")

            # 창이 없으니 채팅·음성으로는 못 준다. 토스트로 알리고 전문은
            # DB·위키에 남긴다 — 다음에 창을 열면 거기서 볼 수 있다.
            if routine.wants("notify") or routine.wants("chat"):
                # 누르면 아이리스가 뜨고 이 루틴 노트가 열린다.
                show_toast(
                    routine.name,
                    notify_summary(routine, body),
                    launch=routine_uri(routine.id),
                )
            if routine.wants("wiki"):
                try:
                    wiki.write_inbox_note(
                        f"{routine.name} 실행 결과",
                        format_delivery(routine, body, due.check),
                    )
                except Exception:  # noqa: BLE001
                    pass
            if updated is not None:
                sync_routine_note(wiki, updated)
        return EXIT_OK
    finally:
        db.close()


def run_one(routine_id: int) -> int:
    """루틴 하나를 지금 실행(진단용)."""
    from datetime import datetime

    from iris.runtime.routine_runner import DueRoutine
    from iris.runtime.routine_schedule import OUTCOME_DUE, DueCheck
    from iris.storage.database import Database
    from iris.storage.routines import get_routine, set_next_run

    db = Database()
    try:
        routine = get_routine(db, routine_id)
        if routine is None:
            _log(f"routine {routine_id} not found")
            return EXIT_ERROR
        # 지금 차례로 만들어 두고 공용 경로를 그대로 탄다.
        set_next_run(db, routine_id, datetime.now().isoformat(timespec="seconds"))
    finally:
        db.close()
    return run_tick(force=True)


def _invoke(action: str, args: dict | None = None, *, timeout: float = 8.0) -> dict | None:
    """떠 있는 아이리스의 컨트롤 서피스를 부른다. 못 부르면 None."""
    from iris.system.control_surface import control_state_dir, resolve_control_token

    root = control_state_dir()
    try:
        port = int((root / "control_port").read_text(encoding="utf-8").strip())
        host = (root / "control_host").read_text(encoding="utf-8").strip() or "127.0.0.1"
    except (OSError, ValueError):
        return None
    payload = json.dumps({"action": action, "args": args or {}}).encode("utf-8")
    req = Request(
        f"http://{host}:{port}/v1/invoke",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {resolve_control_token()}",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (URLError, OSError, ValueError, json.JSONDecodeError):
        return None


def _launch_iris() -> bool:
    """아이리스를 새로 띄운다."""
    import subprocess

    try:
        from iris.system.gui_python import gui_launch_env, resolve_gui_pythonw

        runner = resolve_gui_pythonw(_ROOT)
        env = gui_launch_env(_ROOT)
    except Exception:
        runner = Path(sys.executable)
        pythonw = runner.with_name("pythonw.exe")
        if pythonw.is_file():
            runner = pythonw
        env = None
    try:
        kwargs: dict = {
            "cwd": str(_ROOT),
            "creationflags": getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0),
            "close_fds": True,
        }
        if env is not None:
            kwargs["env"] = env
        subprocess.Popen([str(runner), "-m", "iris"], **kwargs)
    except (OSError, ValueError) as exc:
        _log(f"launch failed: {exc}")
        return False
    return True


def open_target(uri: str) -> int:
    """토스트를 눌렀을 때 — 떠 있으면 앞으로 불러오고, 꺼져 있으면 띄운다."""
    from iris.system.uri_handler import parse_uri

    kind, value = parse_uri(uri)

    if not iris_is_running():
        _log(f"iris not running — launching for {kind}")
        return EXIT_OK if _launch_iris() else EXIT_ERROR

    # 창을 앞으로. 이게 눌렀을 때 사용자가 가장 먼저 기대하는 일이다.
    if _invoke("window.show") is None:
        # 서피스가 응답을 안 한다 — 파일만 남고 죽었을 수 있다.
        return EXIT_OK if _launch_iris() else EXIT_ERROR

    if kind == "routine" and value.isdigit():
        _open_routine_note(int(value))
    return EXIT_OK


def _open_routine_note(routine_id: int) -> None:
    """해당 루틴 노트를 위키에서 연다. 못 찾으면 창만 띄운 채로 둔다."""
    from iris.knowledge.iris_state import routine_rel_path
    from iris.storage.database import Database
    from iris.storage.routines import get_routine

    db = Database()
    try:
        routine = get_routine(db, routine_id)
    finally:
        db.close()
    if routine is None:
        _log(f"routine {routine_id} not found")
        return
    _invoke("wiki.open_note", {"rel_path": f"user/{routine_rel_path(routine)}"})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="iris-routine", description="아이리스 예약 루틴 헤드리스 실행기"
    )
    sub = parser.add_subparsers(dest="command")

    tick = sub.add_parser("tick", help="지금 돌 차례인 루틴 처리 (작업 스케줄러용)")
    tick.add_argument(
        "--force", action="store_true", help="아이리스가 떠 있어도 실행"
    )

    run = sub.add_parser("run", help="루틴 하나를 지금 실행")
    run.add_argument("--id", type=int, required=True)

    opener = sub.add_parser("open", help="토스트 클릭 처리 (URI 스킴 핸들러)")
    opener.add_argument("--uri", default="")

    sub.add_parser("status", help="깨우기 작업·URI 스킴 등록 상태 보기")

    args = parser.parse_args(argv)
    if args.command == "run":
        return run_one(args.id)
    if args.command == "open":
        return open_target(args.uri)
    if args.command == "status":
        from iris.system.routine_wake import query
        from iris.system.uri_handler import query as scheme_query

        st = query()
        sc = scheme_query()
        _log(f"wake registered={st.registered} detail={st.detail}")
        _log(f"uri scheme registered={sc.registered} command={sc.command}")
        return EXIT_OK
    return run_tick(force=bool(getattr(args, "force", False)))


if __name__ == "__main__":
    raise SystemExit(main())
