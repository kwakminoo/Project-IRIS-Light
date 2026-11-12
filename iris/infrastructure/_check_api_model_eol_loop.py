from __future__ import annotations

from iris.infrastructure.api_model_meta import (
    chat_error_hides_model,
    should_skip_api_model_verify,
    state_from_http,
)


def _would_start_verify(state: str, tool_support: str) -> bool:
    return not should_skip_api_model_verify(state, tool_support)


def _count_verify_attempts_after_410() -> int:
    state = ""
    tool = "unknown"
    attempts = 0
    if _would_start_verify(state, tool):
        attempts += 1
        state = state_from_http(
            410,
            "HTTP 410: The model 'moonshotai/kimi-k3' is end of life and no longer available.",
        )
        tool = "unknown"
    if _would_start_verify(state, tool):
        attempts += 1
    return attempts


def main() -> None:
    assert state_from_http(410, "") == "unavailable"
    assert (
        state_from_http(
            410,
            "The model is end of life and no longer available.",
        )
        == "unavailable"
    )
    assert chat_error_hides_model(
        "HTTP 410: The model 'moonshotai/kimi-k3' is end of life and no longer available."
    )
    assert should_skip_api_model_verify("unavailable", "unknown") is True
    assert should_skip_api_model_verify("", "unknown") is False
    assert should_skip_api_model_verify("ok", "yes") is True
    assert _count_verify_attempts_after_410() == 1
    print("api_model_eol_loop self-check ok")


if __name__ == "__main__":
    main()
