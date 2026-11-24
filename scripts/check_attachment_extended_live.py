"""Real Hermes responses through production dispatch, including mixed inputs."""
import json
import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from scripts.check_attachment_live import DispatchHarness, OUT, ROOT
from iris.infrastructure.iris_agent_client import IrisAgentClient
from iris.infrastructure.ollama_client import OllamaClient
from iris.storage.database import Database
from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.workspaces.ide_companion_page import IdeCompanionPage
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout


def run(mode_filter="all", case_filter="all", backend="hermes"):
    OUT.mkdir(parents=True, exist_ok=True)
    fixtures = OUT / "extended"
    (fixtures / "folder/src").mkdir(parents=True, exist_ok=True)
    (fixtures / "folder/docs").mkdir(exist_ok=True)
    (fixtures / "a.txt").write_text("AAA-111", encoding="utf-8")
    (fixtures / "b.txt").write_text("BBB-222", encoding="utf-8")
    (fixtures / "folder/README.md").write_text("PROJECT_CODE=FOLDER-777", encoding="utf-8")
    (fixtures / "folder/src/config.py").write_text('PROJECT_NAME="IRIS_FOLDER_TEST"', encoding="utf-8")
    (fixtures / "folder/docs/guide.md").write_text("User guide", encoding="utf-8")
    app = QApplication.instance() or QApplication([])
    panel = ChatPanel()
    db = Database(OUT / "extended-chat.db")
    harness = DispatchHarness(panel, db)
    panel.send_clicked.connect(harness._on_user_text)
    main = QWidget()
    layout = QVBoxLayout(main)
    layout.addWidget(panel)
    companion = IdeCompanionPage()
    results = []
    suffix = "" if (mode_filter, case_filter) == ("all", "all") else f"-{mode_filter}-{case_filter}"
    backend_suffix = "" if backend == "hermes" else "-" + backend
    result_path = OUT / f"extended{backend_suffix}{suffix}-results.json"
    cases = [
        ("multiple", [fixtures / "a.txt", fixtures / "b.txt"], "두 파일 안의 코드값을 각각 알려줘.", ["AAA-111", "BBB-222"]),
        ("folder-tree", [fixtures / "folder"], "이 폴더 구조를 보여줘.", ["README.md", "config.py", "guide.md"]),
        ("folder-readme", [], "README.md의 PROJECT_CODE를 알려줘. 값만 답해줘.", ["FOLDER-777"]),
        ("folder-followup", [], "src/config.py의 PROJECT_NAME을 알려줘. 값만 답해줘.", ["IRIS_FOLDER_TEST"]),
        ("mixed", [fixtures / "a.txt", fixtures / "folder"], "a.txt의 코드와 src/config.py의 PROJECT_NAME을 각각 알려줘.", ["AAA-111", "IRIS_FOLDER_TEST"]),
        ("project-search", [ROOT], "MCP 관련 코드가 구현된 파일을 찾아서 역할을 설명해줘.", ["iris_control_stdio.py"]),
    ]
    try:
        for mode in ["main", "ide"]:
            if mode_filter != "all" and mode_filter != mode:
                continue
            if mode == "ide":
                companion.mount(orb_spacer=QWidget(), live_activity=QWidget(), chat=panel, activity_height=40)
            for label, paths, query, expected in cases:
                if case_filter != "all" and case_filter != label:
                    continue
                if paths:
                    harness._chat_session.clear_messages()
                before = len(harness.payloads)
                panel._input_area.input_bar._on_paths_attached([str(p) for p in paths])
                panel.set_input_text(query)
                panel._emit_send()
                deadline = time.monotonic() + 60
                while harness._turn_gate.busy and time.monotonic() < deadline:
                    app.processEvents()
                    time.sleep(.01)
                if harness._chat_worker:
                    harness._chat_worker.wait(1000)
                assert len(harness.payloads) > before, harness.failures
                messages = harness.payloads[-1]
                assert all(value in messages[-1]["content"] for value in expected)
                (OUT / f"extended-{mode}-{label}-messages.json").write_text(json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"START {mode} {label}", flush=True)
                try:
                    events = (IrisAgentClient(timeout_sec=55).stream_chat("gemma4:e2b", messages) if backend == "hermes"
                              else OllamaClient("http://127.0.0.1:11434", timeout_sec=55).stream_chat("gemma4:e2b", messages, think=False))
                    answer = "".join(e.get("content") or "" for e in events)
                    passed = all(value in answer for value in expected)
                    result = dict(mode=mode, case=label, expected=expected, answer=answer, passed=passed)
                    harness._chat_session.record("assistant", answer)
                except Exception as exc:
                    result = dict(mode=mode, case=label, passed=False, error=type(exc).__name__ + ": " + str(exc))
                results.append(result)
                result_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps(result, ensure_ascii=False), flush=True)
            if mode == "ide":
                companion.transfer_to(layout, (0, 0, 1))
    finally:
        db._conn.close()
    return all(r["passed"] for r in results)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["all", "main", "ide"], default="all")
    parser.add_argument("--backend", choices=["hermes", "ollama"], default="hermes")
    parser.add_argument("--case", choices=["all", "multiple", "folder-tree", "mixed", "project-search"], default="all")
    args = parser.parse_args()
    raise SystemExit(0 if run(args.mode, args.case, args.backend) else 1)
