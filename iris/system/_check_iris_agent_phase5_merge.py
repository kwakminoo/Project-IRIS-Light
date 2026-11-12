"""Phase 5 Merge decision self-check.

Product speak stays on InternalSidecar (child process). Same-process AIAgent
into the Qt process is declined. Run:

  .venv\\Scripts\\python.exe -m iris.system._check_iris_agent_phase5_merge
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _check_default_source_is_internal_sidecar() -> None:
    from iris.engine.types import InternalSidecar, parse_engine_source

    source = parse_engine_source(None)
    assert isinstance(source, InternalSidecar), type(source)


def _check_chat_worker_prefers_internal_path() -> None:
    from iris.ui.workers import iris_agent_workers as hw
    import inspect

    run_src = inspect.getsource(hw.HermesChatWorker.run)
    assert "_run_internal" in run_src
    assert "ExternalGateway" not in run_src
    assert "_run_external" not in inspect.getsource(hw.HermesChatWorker)
    internal_src = inspect.getsource(hw.HermesChatWorker._run_internal)
    assert "shared_engine" in internal_src
    assert "8642" not in internal_src


def _check_activity_english() -> None:
    text = (ROOT / "iris" / "ui" / "window" / "main_window.py").read_text(
        encoding="utf-8"
    )
    assert 'append_instant_line("No tool calls")' in text
    assert "도구 호출 없음" not in text


def _check_merge_decision_doc() -> None:
    path = ROOT / "docs" / "code-review" / "Iris-Agent-Phase5-merge.md"
    text = path.read_text(encoding="utf-8")
    assert "Merge same-process AIAgent into the Qt process? NO." in text
    assert "InternalSidecar" in text


def main() -> None:
    _check_default_source_is_internal_sidecar()
    _check_chat_worker_prefers_internal_path()
    _check_activity_english()
    _check_merge_decision_doc()
    print(
        "iris_agent_phase5_merge ok",
        "decision=DECLINE_SAME_PROCESS",
        "default=InternalSidecar",
        "activity=english",
        "http8642=retired_from_product",
    )


if __name__ == "__main__":
    main()
