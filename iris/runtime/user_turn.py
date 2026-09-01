from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class UserTurnSource(str, Enum):
    KEYBOARD = "keyboard"
    VOICE = "voice"


@dataclass(frozen=True)
class UserTurn:
    text: str
    source: UserTurnSource
    session_id: int | None = None
    attachments: tuple[str, ...] = ()
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=time.perf_counter)
