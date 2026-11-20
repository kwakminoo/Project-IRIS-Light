"""Real fixture files -> Qt composer -> MainWindow dispatch -> live Hermes responses.

Run from repository root: .venv/Scripts/python.exe -m scripts.check_attachment_live
No provider config mutation; uses the gateway's current inference configuration.
"""
from __future__ import annotations
import argparse
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".iris_light_test_tmp" / "attachment-live"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("IRIS_ATTACHMENT_LOG_DIR", str(OUT))

from PyQt6.QtCore import QObject, QMimeData, QPointF, Qt, QUrl
from PyQt6.QtGui import QDropEvent
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget
from iris.infrastructure.hermes_client import HermesClient
from iris.infrastructure.ollama_client import OllamaClient
from iris.runtime.chat_session import ChatSession
from iris.runtime.chat_turn_gate import ChatTurnGate
from iris.runtime.user_turn_dispatcher import UserTurnDispatcher
from iris.storage.database import Database
from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.window.main_window import MainWindow
from iris.ui.workspaces.ide_companion_page import IdeCompanionPage
from tests.test_attachment_pipeline import create_fixtures


class DispatchHarness(QObject):
    """Production dispatch methods with unrelated startup, TTS and MCP side effects stubbed."""
    _on_user_text = MainWindow._on_user_text
    _execute_user_turn = MainWindow._execute_user_turn
    _continue_user_turn = MainWindow._continue_user_turn
    _format_user_turn_content = MainWindow._format_user_turn_content
    _chat_messages_with_project_context = MainWindow._chat_messages_with_project_context
    _on_attachment_failed = MainWindow._on_attachment_failed

    def __init__(self, panel, db):
        super().__init__()
        self._chat = panel
        self._db = db
        self._chat_session = ChatSession(db)
        self._turn_gate = ChatTurnGate()
        self._turn_dispatcher = UserTurnDispatcher(self)
        self._turn_dispatcher.turn_ready.connect(self._execute_user_turn)
        self._settings = SimpleNamespace(ollama_model="gemma4:e2b", ollama_base_url="http://127.0.0.1:11434", hermes_base_url="http://127.0.0.1:8642/v1", hermes_api_key="", hermes_command="hermes")
        self._saved_model = "gemma4:e2b"
        self._agent_online = True
        self._live_activity = Mock()
        self.payloads = []
        self.failures = []
        for method in ["_try_open_at_path_refs", "_try_local_ide_control", "_try_local_wiki_save", "_try_local_pdf_save", "_try_local_extension_install", "_try_local_workspace_control", "_route_to_workspace_chat", "_handle_image_code_pipe"]:
            setattr(self, method, Mock(return_value=False))
        for method in ["_refresh_context_gauge", "_stop_tts_playback", "_begin_auto_tts_response", "_sync_voice_conversation_state"]:
            setattr(self, method, Mock())

    @property
    def _history(self):
        return self._chat_session.history

    def _current_project_root(self):
        return str(OUT)

    def _use_agent_backend(self):
        return True

    def _is_current_turn(self, tid):
        return self._turn_gate.is_current(tid)

    def _record_history(self, role, content, *, model_content=""):
        self._chat_session.record(role, content, model_content=model_content)

    def _start_chat_worker(self, worker, tid):
        self.payloads.append(worker._messages)
        self._finish_current_turn(tid)

    def _finish_current_turn(self, tid=None, **kwargs):
        tid = self._turn_gate.finish(tid)
        self._chat.set_generating(False)
        self._turn_dispatcher.finish_active_turn(tid)

    def _on_chat_failed_for_turn(self, error, tid):
        self.failures.append(error)
        self._finish_current_turn(tid)


def run(backend="hermes", *, mode_filter="all", format_filter="all", method_filter="all"):
    OUT.mkdir(parents=True, exist_ok=True)
    files = create_fixtures(OUT / "fixtures")
    folder = OUT / "fixtures" / "project"
    folder.mkdir(exist_ok=True)
    (folder / "app.py").write_text("CODE: FOLDER-7777", encoding="utf-8")
    (folder / "node_modules").mkdir(exist_ok=True)
    (folder / "node_modules" / "ignore.txt").write_text("DO_NOT_INCLUDE", encoding="utf-8")
    app = QApplication.instance() or QApplication([])
    panel = ChatPanel()
    panel.set_workspace_root(str(OUT))
    main = QWidget()
    layout = QVBoxLayout(main)
    layout.addWidget(panel)
    companion = IdeCompanionPage()
    database = Database(OUT / "test-chat.db")
    harness = DispatchHarness(panel, database)
    panel.send_clicked.connect(harness._on_user_text)
    results = []
    suffix = "" if (mode_filter, format_filter, method_filter) == ("all", "all", "all") else f"-{mode_filter}-{format_filter}-{method_filter}"
    results_path = OUT / f"{backend}{suffix}-results.json"
    cases = [("txt", files["txt"], "TXT-1234"), ("pdf", files["pdf"], "PDF-5678"), ("pptx", files["pptx"], "PPT-9999"), ("folder", folder, "FOLDER-7777")]
    for mode in ["main", "ide"]:
        if mode_filter != "all" and mode_filter != mode:
            continue
        if mode == "ide":
            companion.mount(orb_spacer=QWidget(), live_activity=QWidget(), chat=panel, activity_height=40)
        for extension, path, expected in cases:
            if format_filter != "all" and format_filter != extension:
                continue
            for method in (["drop"] if extension == "folder" else ["picker", "drop"]):
                if method_filter != "all" and method_filter != method:
                    continue
                harness._chat_session.clear_messages()
                before = len(harness.payloads)
                if method == "drop":
                    mime = QMimeData()
                    mime.setUrls([QUrl.fromLocalFile(str(path))])
                    panel.dropEvent(QDropEvent(QPointF(8, 8), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
                else:
                    panel._input_area.input_bar._on_paths_attached([str(path)])
                panel.set_input_text("첨부된 파일 내용의 CODE 값을 알려줘. CODE 값만 답해줘.")
                panel._emit_send()
                deadline = time.monotonic() + 30
                while len(harness.payloads) == before and time.monotonic() < deadline and not harness.failures:
                    app.processEvents()
                    time.sleep(.01)
                if len(harness.payloads) == before:
                    raise RuntimeError(f"Dispatch failed: {harness.failures}")
                messages = harness.payloads[-1]
                assert expected in messages[-1]["content"], messages[-1]
                assert str(path) not in messages[-1]["content"]
                assert "DO_NOT_INCLUDE" not in messages[-1]["content"]
                # Save fixture-only request context for review. No real user documents/keys.
                (OUT / f"{backend}-{mode}-{extension}-{method}-messages.json").write_text(json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8")
                start = time.monotonic()
                print(f"START {backend} {mode} {extension} {method}", flush=True)
                try:
                    if backend == "hermes":
                        events = HermesClient(timeout_sec=55).stream_chat("gemma4:e2b", messages)
                    else:
                        events = OllamaClient("http://127.0.0.1:11434", timeout_sec=55).stream_chat("gemma4:e2b", messages, think=False)
                    answer = "".join(e.get("content") or "" for e in events)
                    passed = expected in answer and "접근할 수 없" not in answer
                    result = dict(backend=backend, mode=mode, format=extension, method=method, expected=expected, answer=answer, passed=passed, seconds=round(time.monotonic()-start, 2))
                except Exception as exc:
                    result = dict(backend=backend, mode=mode, format=extension, method=method, expected=expected, passed=False, error=str(exc))
                results.append(result)
                print(json.dumps(result, ensure_ascii=False), flush=True)
                results_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        if mode == "ide":
            companion.transfer_to(layout, (0, 0, 1))
    database._conn.close()
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["hermes", "ollama"], default="hermes")
    parser.add_argument("--mode", choices=["all", "main", "ide"], default="all")
    parser.add_argument("--format", choices=["all", "txt", "pdf", "pptx", "folder"], default="all")
    parser.add_argument("--method", choices=["all", "picker", "drop"], default="all")
    args = parser.parse_args()
    raise SystemExit(run(args.backend, mode_filter=args.mode, format_filter=args.format, method_filter=args.method))
