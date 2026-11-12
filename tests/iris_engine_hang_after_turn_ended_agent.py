"""Fake AIAgent: logs Turn ended then hangs before returning.

Mirrors Hermes #131740 (wedge between Turn ended and run_conversation return).
Sidecar must still emit a terminal done/fail on the host pipe.
"""

from __future__ import annotations

import logging
import time


class AIAgent:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.stream_delta_callback = kwargs.get("stream_delta_callback")
        self._persist_disabled = False
        self._session_messages: list[dict] = []

    def run_conversation(self, user_message=None, conversation_history=None, **kwargs):
        callback = self.stream_delta_callback
        if callback is not None:
            callback("hang-")
            callback("answer")
        self._session_messages = [
            {"role": "user", "content": str(user_message or "")},
            {"role": "assistant", "content": "hang-answer"},
        ]
        logging.getLogger("agent.conversation_loop").info(
            "Turn ended: reason=text_response(finish_reason=stop) "
            "model=fake api_calls=1/1 budget=1/1 tool_turns=0 "
            "last_msg_role=assistant response_len=11 session=fake"
        )
        time.sleep(3600)
        return {"final_response": "never-returned"}
