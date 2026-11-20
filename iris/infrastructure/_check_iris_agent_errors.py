"""explain_chat_error: 413 TPM vs context-window messaging."""

from __future__ import annotations

from iris.infrastructure.iris_agent_errors import (
    CONTEXT_LENGTH_USER_MSG,
    TPM_RATE_USER_MSG,
    explain_chat_error,
)

_TPM_UI = TPM_RATE_USER_MSG
_CONTEXT_UI = CONTEXT_LENGTH_USER_MSG

_GROQ_TPM_413 = (
    "Error code: 413 - Request too large for model openai/gpt-oss-120b "
    "on organization ... tokens per minute (TPM): Limit 8000"
)


def main() -> None:
    shown = explain_chat_error(_GROQ_TPM_413)
    assert shown == _TPM_UI, shown
    assert "한 번에 받을 수 있는 길이" not in shown

    assert explain_chat_error(
        "HTTP 413: request too large for model; organization service tier TPM"
    ) == _TPM_UI
    assert "분당" in explain_chat_error("413 tokens per minute exceeded")

    assert explain_chat_error("HTTP 413: payload too large. Cannot compress further.") == _CONTEXT_UI
    assert explain_chat_error("prompt is too long for the model") == _CONTEXT_UI
    assert explain_chat_error("Error 413 context length exceeded") == _CONTEXT_UI
    assert explain_chat_error(_CONTEXT_UI) == _CONTEXT_UI
    print("iris_agent_errors 413 TPM/context self-check ok")


if __name__ == "__main__":
    main()
