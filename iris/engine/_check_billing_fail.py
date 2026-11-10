"""Billing agent results must emit fail, not done."""

from __future__ import annotations

from iris.engine._sidecar_main import agent_result_fail
from iris.engine.types import EngineError, EngineErrorCode
from iris.infrastructure.hermes_errors import explain_chat_error


def main() -> None:
    sample = {
        "failed": True,
        "failure_reason": "billing",
        "final_response": (
            "HTTP 402: You have exhausted your monthly credits. "
            "Please top up your billing entitlement."
        ),
    }
    fail = agent_result_fail(sample)
    assert fail is not None, "billing sample must be fail not done"
    code, detail = fail
    assert code == "billing", code
    assert "402" in detail or "credits" in detail.lower(), detail
    assert agent_result_fail({"final_response": "hello"}) is None
    err = EngineError(EngineErrorCode.BILLING, detail)
    assert "크레딧" in err.user_message
    assert explain_chat_error(err.user_message) == err.user_message
    print("billing_fail self-check ok")


if __name__ == "__main__":
    main()
