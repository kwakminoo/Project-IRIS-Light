"""Transcript API surface for chat history / live turns (T2–T9).

H1 WebEngine host is the primary ChatPanel log. Legacy ChatLogTextEdit may remain
hidden for reopen-note / TTS helpers. Parts stream + append_turn land here.
"""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from PyQt6.QtWidgets import QWidget

from iris.core.message_parts import MessagePart


@runtime_checkable
class TranscriptApi(Protocol):
    def clear(self) -> None: ...

    def append_turn(
        self,
        role: str,
        parts: Sequence[MessagePart],
        *,
        msg_id: str = "",
    ) -> None: ...

    def widget(self) -> QWidget: ...
