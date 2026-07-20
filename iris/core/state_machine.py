"""Iris 앱 상태 머신 (PyQt6 시그널)."""

from __future__ import annotations

from enum import Enum, auto

from PyQt6.QtCore import QObject, pyqtSignal


class AppState(Enum):
    IDLE = auto()
    LISTENING = auto()
    PROCESSING = auto()
    EXECUTING = auto()
    RESPONDING = auto()
    MONITORING = auto()
    ALERTING = auto()
    ERROR = auto()


class StateMachine(QObject):
    """
    상태 전이:
    IDLE -> LISTENING -> PROCESSING -> RESPONDING -> IDLE
    PROCESSING -> EXECUTING -> RESPONDING -> IDLE
    IDLE -> MONITORING -> ALERTING -> IDLE
    오류 시 ERROR -> (복구 후) IDLE
    """

    state_changed = pyqtSignal(object)  # AppState

    def __init__(self) -> None:
        super().__init__()
        self._state = AppState.IDLE

    @property
    def state(self) -> AppState:
        return self._state

    def set_state(self, new_state: AppState) -> None:
        if new_state is self._state:
            return
        self._state = new_state
        self.state_changed.emit(new_state)

    def reset_to_idle(self) -> None:
        self.set_state(AppState.IDLE)

    def to_error(self) -> None:
        self.set_state(AppState.ERROR)
