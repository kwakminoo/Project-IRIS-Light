"""App UI turn event: NDJSON parse, meta helper, worker signal.

Run: .venv\\Scripts\\python.exe -m iris.engine._check_app_ui_event
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from iris.engine import (
    AppUiOfferEvent,
    EngineHome,
    InternalSidecar,
    ToolProgress,
    TurnFinished,
)
from iris.engine._sidecar import parse_turn_event
from iris.engine.app_ui import app_ui_from_tool_meta, emit_app_ui_payload
from iris.infrastructure.iris_agent_client import IrisAgentInferenceTarget
from iris.ui.workers.iris_agent_workers import IrisAgentChatWorker

_FIXTURE = (
    Path(__file__).resolve().parents[1] / "ui" / "chat" / "fixtures" / "app_host_ping.html"
)


class _Engine:
    def __init__(self, events: list) -> None:
        self.source = InternalSidecar(home=EngineHome(Path(".")))
        self._events = events

    def run_turn(self, _turn: object):
        yield from self._events


def main() -> None:
    assert _FIXTURE.is_file(), f"missing fixture {_FIXTURE}"

    tool = parse_turn_event({"t": "tool", "label": "[IRIS tool use: read_file]"})
    assert tool == ToolProgress(label="[IRIS tool use: read_file]")

    raw = {
        "t": "app_ui",
        "title": "앱",
        "html_path": str(_FIXTURE),
        "resource_uri": "ui://ping",
    }
    event = parse_turn_event(raw)
    assert isinstance(event, AppUiOfferEvent)
    assert event.title == "앱"
    assert event.html_path == str(_FIXTURE)
    assert event.resource_uri == "ui://ping"

    from_abs = app_ui_from_tool_meta(
        {"_meta": {"ui": {"resourceUri": str(_FIXTURE)}}},
        default_title="핑",
    )
    assert from_abs == AppUiOfferEvent(
        title="핑", html_path=str(_FIXTURE), resource_uri=str(_FIXTURE)
    )

    file_uri = _FIXTURE.as_uri()
    from_file = app_ui_from_tool_meta({"ui": {"resourceUri": file_uri}})
    assert from_file is not None
    assert Path(from_file.html_path).resolve() == _FIXTURE.resolve()
    assert from_file.resource_uri == file_uri

    from_name = app_ui_from_tool_meta({"ui": {"resourceUri": "app_host_ping.html"}})
    assert from_name is not None
    assert Path(from_name.html_path).resolve() == _FIXTURE.resolve()

    assert app_ui_from_tool_meta(None) is None
    assert app_ui_from_tool_meta({"ui": {"resourceUri": ""}}) is None
    assert app_ui_from_tool_meta({"ui": {"resourceUri": "https://example.com/x.html"}}) is None
    assert app_ui_from_tool_meta({"ui": {"resourceUri": "ui://host/../secret"}}) is None
    stub = app_ui_from_tool_meta({"ui": {"resourceUri": "ui://ping"}}, default_title="원격")
    assert stub == AppUiOfferEvent(title="원격", html_path="", resource_uri="ui://ping")
    stub_payload = emit_app_ui_payload({"_meta": {"ui": {"resourceUri": "ui://weather/card"}}})
    assert stub_payload == {
        "t": "app_ui",
        "title": "앱",
        "html_path": "",
        "resource_uri": "ui://weather/card",
    }

    offers: list[tuple[str, str, str]] = []
    tools: list[str] = []
    worker = IrisAgentChatWorker(
        "llama",
        [{"role": "user", "content": "hi"}],
        target=IrisAgentInferenceTarget(model="llama", provider="custom"),
    )
    worker.app_ui.connect(lambda title, path, uri: offers.append((title, path, uri)))
    worker.tool_progress.connect(tools.append)
    engine = _Engine(
        [
            ToolProgress("[IRIS tool use: read_file]"),
            AppUiOfferEvent(title="앱", html_path=str(_FIXTURE), resource_uri="ui://ping"),
            AppUiOfferEvent(title="원격", html_path="", resource_uri="ui://weather/card"),
            TurnFinished("ok"),
        ]
    )
    with (
        patch.object(IrisAgentChatWorker, "_wire_native_speak_tools", lambda self: None),
        patch("iris.ui.workers.iris_agent_workers.shared_engine", return_value=engine),
        patch("iris.ui.workers.iris_agent_workers._engine_source", return_value=engine.source),
    ):
        worker.run()
    assert tools == ["[IRIS tool use: read_file]"]
    assert offers == [
        ("앱", str(_FIXTURE), "ui://ping"),
        ("원격", "", "ui://weather/card"),
    ]
    print("app_ui event ok")


if __name__ == "__main__":
    main()
