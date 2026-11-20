"""api_server pin keeps computer_use listed; product chat disables it.

Sidecar / config ``disabled_toolsets`` must include ``computer_use`` so the
model never sees Hermes desktop control. ``platform_toolsets.api_server`` may
still name ``hermes-api-server`` + ``computer_use`` for legacy gateway compat.

Static pin≠chat lock (no live config write): ``_check_toolset_platform_chat_boundary``,
also under ``_check_agent_merge_policy_closed``.
"""

from __future__ import annotations


def main() -> None:
    from iris.system.iris_agent_control_sync import (
        _IRIS_API_SERVER_TOOLSETS,
        _IRIS_DISABLED_TOOLSETS,
        _merge_api_server_toolsets,
        ensure_iris_agent_api_server_computer_use,
        ensure_iris_agent_disabled_terminal,
        read_iris_agent_api_server_toolsets,
        read_iris_agent_disabled_toolsets,
        verify_iris_agent_api_server_computer_use,
        verify_iris_agent_terminal_disabled,
    )

    assert "hermes-api-server" in _IRIS_API_SERVER_TOOLSETS
    assert "computer_use" in _IRIS_API_SERVER_TOOLSETS
    merged = _merge_api_server_toolsets(["custom-extra"])
    assert merged[0] == "custom-extra"
    assert "hermes-api-server" in merged and "computer_use" in merged

    ensure_iris_agent_disabled_terminal()
    ok_term, term_msg = verify_iris_agent_terminal_disabled()
    assert ok_term, term_msg
    disabled = read_iris_agent_disabled_toolsets()
    assert "terminal" in disabled and "browser" in disabled, disabled
    assert "computer_use" in disabled, disabled
    assert "computer_use" in _IRIS_DISABLED_TOOLSETS
    assert all(n in _IRIS_DISABLED_TOOLSETS for n in ("terminal", "browser"))

    ensure_iris_agent_api_server_computer_use()
    ok_cu, cu_msg = verify_iris_agent_api_server_computer_use()
    assert ok_cu, cu_msg
    api = read_iris_agent_api_server_toolsets()
    assert "hermes-api-server" in api and "computer_use" in api, api
    print("hermes_computer_use_enabled check ok", cu_msg, "disabled_has_computer_use")


if __name__ == "__main__":
    main()
