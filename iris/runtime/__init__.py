"""Runtime helpers for conversation turn dispatch.

Agent-readable:
- Owns: UserTurn model + UserTurnDispatcher (text/voice → conversation turn).
- Does not: PyQt widgets, Ollama/Hermes HTTP, or skill markdown.
- Talks to: UI chat submit path, voice STT results, Gateway session boundary.
- Extend via: intents near dispatcher; new agent tools go to Hermes skills/MCP, not here.
"""

from .user_turn import UserTurn, UserTurnSource
from .user_turn_dispatcher import UserTurnDispatcher

__all__ = ["UserTurn", "UserTurnDispatcher", "UserTurnSource"]
