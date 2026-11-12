"""Iris Agent product façade (≤10 exports).

Thin re-exports only. Backing logic lives in ``iris_agent_*`` modules;
``hermes_*`` files are Unit 7 re-export shims. Worker symbols load lazily so
``home`` / ``ensure_runtime`` stay Qt-free.
"""

from __future__ import annotations

from typing import Any

from iris.infrastructure.agent_runtime import (
    ensure_iris_agent_runtime,
    iris_agent_home,
    load_pinned_sha,
)
from iris.infrastructure.agent_tool_registry import speak_invoke_agent_tool as speak_invoke

home = iris_agent_home
ensure_runtime = ensure_iris_agent_runtime
pin_sha = load_pinned_sha

__all__ = [
    "home",
    "iris_agent_home",
    "ensure_runtime",
    "ensure_iris_agent_runtime",
    "IrisAgentHealthWorker",
    "IrisAgentChatWorker",
    "IrisAgentControlSyncWorker",
    "IrisAgentModelSyncWorker",
    "speak_invoke",
    "pin_sha",
]

_WORKER_NAMES = frozenset(
    {
        "IrisAgentHealthWorker",
        "IrisAgentChatWorker",
        "IrisAgentControlSyncWorker",
        "IrisAgentModelSyncWorker",
    }
)


def __getattr__(name: str) -> Any:
    if name in _WORKER_NAMES:
        from iris.ui.workers import iris_agent_workers as hw

        mapping = {
            "IrisAgentHealthWorker": hw.IrisAgentHealthWorker,
            "IrisAgentChatWorker": hw.IrisAgentChatWorker,
            "IrisAgentControlSyncWorker": hw.IrisAgentControlSyncWorker,
            "IrisAgentModelSyncWorker": hw.IrisAgentModelSyncWorker,
        }
        for key, value in mapping.items():
            globals()[key] = value
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
