"""Unit — one default Speak/Agent harness (no per-family profiles).

Fails when:
  - iris/system/harness_profiles (or sibling family profile module) exists
  - speak allowlist is not PHASE4 / default_agent_tools
  - SyncReport.summary_line still uses Iris↔Hermes
  - setup/settings product strings still bare-brand Hermes
    (delegates to ``_check_iris_agent_branding``)

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_default_agent_harness
"""

from __future__ import annotations

from pathlib import Path

from iris.infrastructure.tool_capability import PHASE4_ALLOWLIST, default_agent_tools
from iris.system.iris_agent_control_sync import SyncReport, project_root

_REPO = project_root()
_FORBIDDEN_PROFILE_DIRS = (
    _REPO / "iris" / "system" / "harness_profiles",
    _REPO / "iris" / "infrastructure" / "harness_profiles",
    _REPO / "iris" / "system" / "model_family_profiles",
)
_FORBIDDEN_PROFILE_MODULES = (
    _REPO / "iris" / "system" / "harness_profiles.py",
    _REPO / "iris" / "infrastructure" / "harness_profiles.py",
    _REPO / "iris" / "system" / "nvidia_harness.py",
    _REPO / "iris" / "system" / "qwen_harness.py",
    _REPO / "iris" / "system" / "gpt_oss_harness.py",
)


def _assert_no_family_harness_profiles() -> None:
    for path in _FORBIDDEN_PROFILE_DIRS:
        assert not path.exists(), f"family harness profile dir must not exist: {path}"
    for path in _FORBIDDEN_PROFILE_MODULES:
        assert not path.exists(), f"family harness module must not exist: {path}"


def _assert_single_speak_allowlist() -> None:
    names = default_agent_tools().engine_names()
    assert names, "default_agent_tools().engine_names() empty"
    expected = PHASE4_ALLOWLIST.names()
    assert tuple(sorted(names)) == expected, (
        f"speak allowlist must be PHASE4 only: got {tuple(names)!r} "
        f"expected {expected!r}"
    )
    assert "control.invoke" in names
    for bad in ("iris_get_state", "iris_get_catalog", "iris_invoke"):
        assert bad not in names, f"MCP triple name still in speak tools: {bad}"


def _assert_summary_line_iris_agent() -> None:
    fail_line = SyncReport(ok=False, mcp_installed=False, errors=["boom"]).summary_line()
    ok_line = SyncReport(ok=True, mcp_installed=True).summary_line()
    assert fail_line.startswith("Iris↔Agent"), fail_line
    assert ok_line.startswith("Iris↔Agent:"), ok_line
    assert "Iris↔Hermes" not in fail_line and "Iris↔Hermes" not in ok_line
    assert "MCP iris-control ok" not in ok_line


def _assert_iris_agent_branding() -> None:
    from iris.system._check_iris_agent_branding import _main as branding_main

    branding_main()


def _main() -> None:
    _assert_no_family_harness_profiles()
    _assert_single_speak_allowlist()
    _assert_summary_line_iris_agent()
    _assert_iris_agent_branding()
    print("default_agent_harness ok")
    print(f"  speak tools: {len(PHASE4_ALLOWLIST.names())} (PHASE4 / default_agent_tools)")
    print(f"  summary: {SyncReport(ok=True, mcp_installed=True).summary_line()}")


if __name__ == "__main__":
    _main()
