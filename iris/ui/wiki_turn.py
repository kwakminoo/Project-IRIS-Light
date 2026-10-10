"""위키 명령 실행.

채팅 턴은 wiki_requests_go_to_hermes 가 참이면 여기서 닫지 않는다.
"""

from __future__ import annotations

from iris.knowledge.wiki_command import WikiCommand, parse_wiki_command
from iris.runtime.user_turn import UserTurn


def wiki_requests_go_to_hermes() -> bool:
    """위키 채팅은 키워드 명령으로 턴을 닫지 않는다. Hermes 도구가 실행한다."""
    return True


def try_wiki_command(window: object, turn: UserTurn) -> bool:
    command = parse_wiki_command(
        turn.text,
        turn.attachments,
        getattr(window, "_history", ()),
        target=str(getattr(window, "_wiki_last_rel", "") or ""),
    )
    if command is None:
        return False
    _echo_user(window, turn)
    _start(window, command, turn.id)
    return True


def note_wiki_tool(window: object, message: str) -> None:
    text = (message or "").strip().lower()
    if not text.endswith(" ok") and " ok " not in f" {text} ":
        return
    if "wiki.open_note" in text:
        window._wiki_turn_opened = True
    if "wiki.move_notes" in text:
        window._wiki_turn_moved = True
        window._wiki_turn_wrote = True
        window._wiki_turn_changed = True
    writers = (
        "wiki.write_user_note",
        "wiki.import_content",
        "wiki.import_pages",
        "wiki.reprocess_note",
        "wiki.delete_note",
    )
    if any(name in text for name in writers):
        window._wiki_turn_wrote = True
        window._wiki_turn_changed = True


def _echo_user(window: object, turn: UserTurn) -> None:
    display = window._format_user_turn_content(turn)
    panel = window._active_workspace_iris_panel()
    if panel is not None:
        panel.append_user(display)
    else:
        window._chat.append_message_instant("You", display)
    window._record_history("user", display)


def _say(window: object, message: str) -> None:
    panel = window._active_workspace_iris_panel()
    if panel is not None:
        panel.end_iris(message)
    else:
        window._chat.append_message_instant("Iris", message)
    window._record_history("assistant", message)
    window._refresh_context_gauge()


def _remember(window: object, result: dict) -> None:
    rel = str(result.get("rel_path") or "").replace("\\", "/")
    if result.get("op") == "delete":
        if getattr(window, "_wiki_last_rel", "") == rel:
            window._wiki_last_rel = ""
        return
    if rel:
        window._wiki_last_rel = rel
    if result.get("wrote"):
        window._wiki_turn_wrote = True
        window._wiki_turn_changed = bool(result.get("changed"))


def _show_note(window: object, result: dict) -> None:
    rel = str(result.get("rel_path") or "")
    op = str(result.get("op") or "")
    if not rel:
        return
    if op == "delete":
        try:
            window._obsidian_page.reload_graph()
            window._left_sidebar.obsidian_detail.reload()
        except Exception:
            pass
        return
    open_ops = {"open", "reprocess", "create", "update"}
    if op in open_ops or result.get("mode") == "reprocess":
        window._open_saved_wiki_note(rel)
        window._wiki_turn_opened = True


def _chat_line(window: object, result: dict) -> str:
    op = str(result.get("op") or "")
    if op in ("delete", "list") and result.get("message"):
        return str(result["message"])
    if op == "open":
        return f"열었습니다.\n`{result.get('rel_path') or ''}`"
    return window._wiki_import_success_message(result)


def _present(window: object, result: dict) -> None:
    _remember(window, result)
    _show_note(window, result)
    line = _chat_line(window, result)
    _say(window, line)
    rel = str(result.get("rel_path") or "")
    if rel:
        window._live_activity.append_instant_line(f"wiki.{result.get('op')} ok {rel}")


def _fail(window: object, turn_id: str, err: str) -> None:
    window._busy = False
    window._chat.set_generating(False)
    _say(window, f"위키 처리 실패: {err}")
    window._finish_current_turn(turn_id, open_followup=False)


def _on_ok(window: object, turn_id: str, result: dict) -> None:
    try:
        window._busy = False
        window._chat.set_generating(False)
        _present(window, result if isinstance(result, dict) else {})
        window._finish_current_turn(turn_id, open_followup=False)
    except Exception as exc:  # noqa: BLE001 — 슬롯 예외는 프로세스를 죽인다
        try:
            _fail(window, turn_id, str(exc))
        except Exception:
            pass


def _on_err(window: object, turn_id: str, err: str) -> None:
    try:
        _fail(window, turn_id, err or "위키 처리 실패")
    except Exception:
        pass


def _filing(window: object) -> dict:
    try:
        from iris.knowledge.wiki_filing import filing_kwargs

        root = ""
        try:
            root = str(window._current_project_root() or "")
        except Exception:
            root = ""
        model = (
            window._chat.current_model()
            or (getattr(window, "_saved_model", None) or "").strip()
            or (window._settings.ollama_model or "").strip()
        )
        return filing_kwargs(
            db=window._db,
            base_url=window._settings.ollama_base_url,
            history_settings=window._model_switch.history_settings,
            model=model,
            project_root=root,
            settings=window._settings,
        )
    except Exception:
        return {}


def _start(window: object, command: WikiCommand, turn_id: str) -> None:
    if not command.needs_model():
        try:
            from iris.knowledge.wiki_ops import execute_wiki_command

            result = execute_wiki_command(
                window._iris_wiki,
                command,
                filing=_filing(window),
            )
        except Exception as exc:  # noqa: BLE001
            _fail(window, turn_id, str(exc))
            return
        try:
            _present(window, result)
            window._finish_current_turn(turn_id, open_followup=False)
        except Exception as exc:  # noqa: BLE001
            _fail(window, turn_id, str(exc))
        return

    worker = getattr(window, "_wiki_import_worker", None)
    if worker is not None and worker.isRunning():
        _say(window, "이전 위키 작업이 아직 진행 중입니다.")
        window._finish_current_turn(turn_id, open_followup=False)
        return
    model = (
        window._chat.current_model()
        or (getattr(window, "_saved_model", None) or "").strip()
        or (window._settings.ollama_model or "").strip()
    )
    if not model:
        _fail(window, turn_id, "요약·번역에는 모델 선택이 필요합니다.")
        return
    window._chat.append_message_instant("Iris", "노트를 정리하는 중…")
    window._live_activity.append_instant_line(f"wiki.{command.op} start")
    window._busy = True
    window._chat.set_generating(True)
    from iris.ui.workers.wiki_import_worker import WikiCommandWorker

    job = WikiCommandWorker(
        window._iris_wiki,
        command,
        model=model,
        ollama_base_url=window._settings.ollama_base_url,
        db=window._db,
        project_root=window._current_project_root(),
        settings=window._settings,
        parent=window,
    )
    job.finished_ok.connect(lambda result, tid=turn_id: _on_ok(window, tid, result))
    job.finished_err.connect(lambda err, tid=turn_id: _on_err(window, tid, err))
    window._wiki_import_worker = job
    job.start()


def _check() -> None:
    from pathlib import Path

    from iris.knowledge.wiki_command import parse_wiki_command

    assert wiki_requests_go_to_hermes() is True
    caught = parse_wiki_command("위키에서 내용들을 삭제해주고 영어 제목 폴더를 만들어 챕터폴더들을 통째로 옮겨줘")
    assert caught is not None and caught.op == "delete"
    main = Path(__file__).resolve().parents[2] / "iris" / "ui" / "window" / "main_window.py"
    src = main.read_text(encoding="utf-8")
    assert "wiki_requests_go_to_hermes()" in src
    assert "if try_wiki_command" not in src
    assert "if self._try_local_wiki_save" not in src
    from iris.ui.control_actions.wiki import page_note_rows

    page = page_note_rows(list(range(120)))
    assert page["total"] == 120 and page["count"] == 40 and page["truncated"] is True
    print("wiki_turn gate ok")


if __name__ == "__main__":
    _check()
