"""Ctor contracts for Iris Agent workers. Stale kwargs abort Qt slots."""

from __future__ import annotations

import inspect
from pathlib import Path

from iris.ui.workers.iris_agent_workers import IrisAgentChatWorker, IrisAgentHealthWorker


def main() -> None:
    health_params = list(inspect.signature(IrisAgentHealthWorker.__init__).parameters)
    assert health_params == ["self", "parent"], health_params
    chat_params = list(inspect.signature(IrisAgentChatWorker.__init__).parameters)
    assert chat_params == [
        "self",
        "model",
        "messages",
        "target",
        "attempts",
        "parent",
    ], chat_params
    mw = (Path(__file__).resolve().parents[1] / "window" / "main_window.py").read_text(
        encoding="utf-8"
    )
    text = mw.replace("\r\n", "\n")
    assert "IrisAgentHealthWorker(parent=self)" in text
    assert "IrisAgentHealthWorker(\n            self._settings.hermes_base_url" not in text
    assert "api_key=self._settings.hermes_api_key" not in text.split("IrisAgentChatWorker(")[1].split(
        ")"
    )[0]
    assert "IrisAgentChatWorker(\n                target.model or model," in text
    print("hermes_worker_ctors ok")


if __name__ == "__main__":
    main()
