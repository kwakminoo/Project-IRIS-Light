"""Hermes 내장 terminal/browser/web/code_execution 등 toolset 비활성 계약 자검."""

from __future__ import annotations

_REQUIRED = frozenset(
    {
        "file",
        "terminal",
        "web",
        "code_execution",
        "memory",
        "delegation",
        "clarify",
        "browser",
        "browser-use",
        "browser-cdp",
        "computer_use",
        "tts",
        "vision",
    }
)


def main() -> None:
    from iris.system.iris_agent_control_sync import (
        _IRIS_DISABLED_TOOLSETS,
        _merge_disabled_toolsets,
        ensure_iris_agent_disabled_terminal,
        read_iris_agent_disabled_toolsets,
        verify_iris_agent_terminal_disabled,
    )

    missing_const = sorted(_REQUIRED - set(_IRIS_DISABLED_TOOLSETS))
    assert not missing_const, f"_IRIS_DISABLED_TOOLSETS missing {missing_const}"
    merged = _merge_disabled_toolsets(["custom"])
    missing_merged = sorted(_REQUIRED - set(merged))
    assert not missing_merged, f"merge missing {missing_merged}"
    assert "custom" in merged
    ensure_iris_agent_disabled_terminal()
    ok, msg = verify_iris_agent_terminal_disabled()
    assert ok, msg
    names = read_iris_agent_disabled_toolsets()
    missing_cfg = sorted(_REQUIRED - set(names))
    assert not missing_cfg, f"config disabled missing {missing_cfg}; have={names}"
    print("hermes_terminal_disabled check ok", msg)


if __name__ == "__main__":
    main()
