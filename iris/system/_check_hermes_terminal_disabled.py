"""Hermes 내장 terminal/browser toolset 비활성 계약 자검."""

from __future__ import annotations


def main() -> None:
    from iris.system.iris_agent_control_sync import (
        _IRIS_DISABLED_TOOLSETS,
        _merge_disabled_toolsets,
        ensure_hermes_disabled_terminal,
        read_hermes_disabled_toolsets,
        verify_hermes_terminal_disabled,
    )

    assert "terminal" in _IRIS_DISABLED_TOOLSETS and "browser" in _IRIS_DISABLED_TOOLSETS
    merged = _merge_disabled_toolsets(["web"])
    assert "terminal" in merged and "browser" in merged and "web" in merged
    # web 은 끄지 않는다 — merge 만 하고 web 을 disabled 필수에 넣지 않음
    ensure_hermes_disabled_terminal()
    ok, msg = verify_hermes_terminal_disabled()
    assert ok, msg
    names = read_hermes_disabled_toolsets()
    assert "terminal" in names and "browser" in names, names
    print("hermes_terminal_disabled check ok", msg)


if __name__ == "__main__":
    main()
