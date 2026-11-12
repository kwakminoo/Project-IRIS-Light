"""Hermes api_server computer_use 활성 + terminal/browser 비활성 계약 자검."""

from __future__ import annotations


def main() -> None:
    from iris.system.iris_agent_control_sync import (
        _IRIS_API_SERVER_TOOLSETS,
        _IRIS_DISABLED_TOOLSETS,
        _merge_api_server_toolsets,
        ensure_hermes_api_server_computer_use,
        ensure_hermes_disabled_terminal,
        read_hermes_api_server_toolsets,
        read_hermes_disabled_toolsets,
        verify_hermes_api_server_computer_use,
        verify_hermes_terminal_disabled,
    )

    assert "hermes-api-server" in _IRIS_API_SERVER_TOOLSETS
    assert "computer_use" in _IRIS_API_SERVER_TOOLSETS
    merged = _merge_api_server_toolsets(["custom-extra"])
    assert merged[0] == "custom-extra"
    assert "hermes-api-server" in merged and "computer_use" in merged

    ensure_hermes_disabled_terminal()
    ok_term, term_msg = verify_hermes_terminal_disabled()
    assert ok_term, term_msg
    disabled = read_hermes_disabled_toolsets()
    assert "terminal" in disabled and "browser" in disabled, disabled
    assert "computer_use" not in disabled, disabled
    assert all(n in _IRIS_DISABLED_TOOLSETS for n in ("terminal", "browser"))

    ensure_hermes_api_server_computer_use()
    ok_cu, cu_msg = verify_hermes_api_server_computer_use()
    assert ok_cu, cu_msg
    api = read_hermes_api_server_toolsets()
    assert "hermes-api-server" in api and "computer_use" in api, api
    print("hermes_computer_use_enabled check ok", cu_msg)


if __name__ == "__main__":
    main()
