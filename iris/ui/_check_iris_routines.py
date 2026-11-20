"""실제 MainWindow 로 IRIS 칸 + 루틴 한 바퀴.

사용자의 진짜 위키를 건드리지 않도록 임시 위키로 갈아끼운다. 모델 호출은
하지 않는다 — 워커 없이 결과를 직접 넣어 배선만 확인한다.
"""

from __future__ import annotations

import sys
import tempfile
from datetime import datetime
from pathlib import Path

from iris.ui.qt_bootstrap import ensure_qt_webengine_ready


def main() -> None:
    ensure_qt_webengine_ready()
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)

    from iris.knowledge.history_store import list_entries
    from iris.knowledge.iris_state import IRIS_DIR
    from iris.knowledge.iris_wiki import IrisWiki
    from iris.runtime.model_switch import ModelSwitchService
    from iris.runtime.routine_runner import DueRoutine
    from iris.runtime.routine_schedule import OUTCOME_DUE, DueCheck
    from iris.storage.database import Database
    from iris.storage.routines import create_routine, get_routine
    from iris.ui.window.main_window import MainWindow

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        win = MainWindow(test_mode=True)
        app.processEvents()

        for attr in ("_routine_worker", "_routine_in_flight", "_iris_state_cache"):
            assert hasattr(win, attr), f"MainWindow.__init__ 이 {attr} 를 안 만든다"

        db = Database(root / "routines.db")
        wiki = IrisWiki(docs_root=root / "docs", user_root=root / "wiki")
        win._iris_wiki = wiki
        win._model_switch = ModelSwitchService(db, wiki=wiki)
        win._conversation_id = 1
        win._history = []
        win._pending_handoff = ""
        real_db = win._db
        win._db = db
        try:
            # 1) 상태 스냅샷이 IRIS 칸에 써지고 키는 안 새야 한다
            win._settings.agent_api_key = "sk-must-not-leak"
            win._sync_iris_wiki()
            index_path = wiki.user_root / IRIS_DIR / "index.md"
            assert index_path.is_file(), "IRIS/index.md 가 안 생김"
            index = index_path.read_text(encoding="utf-8")
            assert "# IRIS" in index
            assert "sk-must-not-leak" not in index, "키가 위키로 샜다"
            print("  IRIS 칸 생성 · 키 미노출 ok")

            # 2) 루틴 등록 → 칸에 카드가 뜬다
            routine = create_routine(
                db,
                name="아침 뉴스 브리핑",
                task="오늘 주요 뉴스 3개를 한 줄씩 정리해줘",
                time_of_day="09:00",
                now=datetime(2026, 9, 29, 8, 0),
            )
            win._sync_iris_wiki(routine=routine, change=f"루틴 등록: {routine.name}")
            index = index_path.read_text(encoding="utf-8")
            assert "아침 뉴스 브리핑" in index
            assert "매일 09:00" in index and "채팅 · 알림" in index
            note = (wiki.user_root / IRIS_DIR / "routines" / "아침-뉴스-브리핑.md")
            assert note.is_file(), "루틴 노트가 안 생김"
            assert "오늘 주요 뉴스 3개" in note.read_text(encoding="utf-8")
            print("  루틴 등록 · 카드 + 노트 ok")

            # 3) 등록·변경이 History 에도 남는다
            marks = [e for e in list_entries(db) if e.tags == "iris-state"]
            assert marks, "IRIS 상태 변경이 History 에 안 남았다"
            assert any("루틴 등록" in e.body for e in marks)
            print(f"  History 기록 {len(marks)}건 ok")

            # 4) 실행 결과 전달 — 채팅·알림 배선 (모델 호출 없이)
            due = DueRoutine(
                routine=routine,
                check=DueCheck(outcome=OUTCOME_DUE, scheduled_for="2026-09-29T09:00:00"),
            )
            win._routine_in_flight = due
            win._routine_worker = object()  # 워커가 있는 척
            win._on_routine_finished(routine.id, "1. 뉴스A\n2. 뉴스B\n3. 뉴스C")
            app.processEvents()

            after = get_routine(db, routine.id)
            assert after.run_count == 1, after.run_count
            assert after.last_status == "ok"
            assert "뉴스A" in after.last_result
            assert after.next_run_at == "2026-09-30T09:00:00", after.next_run_at
            assert win._routine_worker is None and win._routine_in_flight is None
            note_text = note.read_text(encoding="utf-8")
            assert "실행 1회" in note_text and "뉴스A" in note_text
            print(f"  실행 결과 기록 · 다음 예약 {after.next_run_at} ok")

            # 5) 늦은 결과가 엉뚱한 루틴에 붙지 않아야 한다
            win._routine_in_flight = None
            win._on_routine_finished(routine.id, "버려져야 할 결과")
            assert get_routine(db, routine.id).run_count == 1
            print("  떠돌이 결과 무시 ok")

            # 6) 지금 실행 (예약 무시) — 모델이 없으면 깔끔히 거절
            win._settings.ollama_model = ""
            assert win._run_routine_now(routine) is False
            print("  모델 미선택 시 거절 ok")

            # 7) MCP 액션이 실제로 등록되고 호출된다
            from iris.system.control_surface import ActionRegistry
            from iris.ui.control_actions.routine import register_routine_actions

            reg = ActionRegistry()
            register_routine_actions(win, reg)
            listed = reg.invoke("routine.list", {})
            assert listed.get("ok") is True, listed
            names = [r["name"] for r in listed["result"]["routines"]]
            assert "아침 뉴스 브리핑" in names, names

            made = reg.invoke(
                "routine.create",
                {"task": "매주 금요일에 주간 메일 정리해줘", "kind": "weekly",
                 "time_of_day": "18:00", "weekdays": "fri", "deliver": "채팅"},
            )
            assert made.get("ok") is True, made
            assert made["result"]["routine"]["deliver"] == "chat"
            assert made["result"]["routine"]["schedule"].startswith("매주 금")

            paused = reg.invoke("routine.update", {"name": "아침 뉴스 브리핑", "enabled": False})
            assert paused.get("ok") is True and paused["result"]["routine"]["enabled"] is False

            gone = reg.invoke("routine.delete", {"name": "아침 뉴스 브리핑"})
            assert gone.get("ok") is True
            assert reg.invoke("routine.get", {"name": "아침 뉴스 브리핑"}).get("ok") is False
            assert reg.invoke("routine.create", {"task": "  "}).get("ok") is False
            print("  MCP 액션 create/list/update/delete ok")

            win.close()
            app.processEvents()
            win.deleteLater()
            app.processEvents()
        finally:
            win._db = real_db
            db.close()

    print("iris_routines smoke ok")


if __name__ == "__main__":
    main()
