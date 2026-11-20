"""CLOSED backlog lock — slot D REPLACE + Qt merge NO-GO + toolset boundary.

Asserts permanent product policies without implementing merge:

1) Hermes file/terminal slot D — REPLACE via Iris familiar/model_tool_names.
   Sidecar keeps disabled_toolsets (never re-enable Hermes).
2) Qt in-process AIAgent merge — Phase1 / Phase5 Decision NO-GO.
   MainWindow must not import AIAgent; product EngineSource is InternalSidecar.
3) ToolsetBoundary — api_server pin may list hermes-api-server + computer_use;
   product chat disabled_toolsets (== _IRIS_DISABLED_TOOLSETS) still disables
   computer_use so the model never sees Hermes desktop control.

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_agent_merge_policy_closed
"""

from __future__ import annotations

from iris.engine._check_sidecar_disables_agent_file_terminal import main as _slot_d
from iris.engine._check_iris_agent_sidecar_only import main as _sidecar_only
from iris.system._check_iris_agent_phase5_merge import main as _qt_merge
from iris.system._check_toolset_platform_chat_boundary import main as _toolset_boundary


def main() -> None:
    _slot_d()
    _sidecar_only()
    _qt_merge()
    _toolset_boundary()
    print(
        "agent_merge_policy_closed ok",
        "slot_d=CLOSED:REPLACE",
        "qt_merge=CLOSED:NO-GO",
        "toolset_boundary=CLOSED:pin≠chat",
    )


if __name__ == "__main__":
    main()
