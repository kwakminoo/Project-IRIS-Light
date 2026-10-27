from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal, NewType, Union

from iris.infrastructure.hermes_client import HermesInferenceTarget


class Role(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


UserUtterance = NewType("UserUtterance", str)
# Last user text of a turn. Not interchangeable with assistant content.


class EngineErrorCode(Enum):
    NOT_INSTALLED = "not_installed"
    WRONG_PYTHON = "wrong_python"
    SPAWN_FAILED = "spawn_failed"
    SIDECAR_DIED = "sidecar_died"
    PROTOCOL = "protocol"
    AUTH = "auth"
    CANCELLED = "cancelled"
    NO_USER_UTTERANCE = "no_user_utterance"
    TOOL_TRANSPORT = "tool_transport"
    UNKNOWN = "unknown"


_USER_MESSAGES = {
    EngineErrorCode.NOT_INSTALLED: "엔진이 아직 설치되지 않았습니다.",
    EngineErrorCode.WRONG_PYTHON: "엔진 Python이 IRIS와 다릅니다.",
    EngineErrorCode.SPAWN_FAILED: "엔진을 시작하지 못했습니다.",
    EngineErrorCode.SIDECAR_DIED: "엔진 프로세스가 종료되었습니다.",
    EngineErrorCode.PROTOCOL: "엔진 응답을 읽지 못했습니다.",
    EngineErrorCode.AUTH: "엔진 인증에 실패했습니다.",
    EngineErrorCode.CANCELLED: "요청이 취소되었습니다.",
    EngineErrorCode.NO_USER_UTTERANCE: "보낼 사용자 메시지가 없습니다.",
    EngineErrorCode.TOOL_TRANSPORT: "도구 호출에 실패했습니다.",
    EngineErrorCode.UNKNOWN: "엔진에서 알 수 없는 오류가 났습니다.",
}


@dataclass(frozen=True)
class EngineError(Exception):
    code: EngineErrorCode
    detail: str

    def __str__(self) -> str:
        return self.detail

    @property
    def user_message(self) -> str:
        return _USER_MESSAGES.get(self.code, _USER_MESSAGES[EngineErrorCode.UNKNOWN])


@dataclass(frozen=True)
class ChatTranscript:
    """IRIS history for one send. No Hermes session id exists on this type."""

    messages: tuple[ChatMessage, ...]

    @classmethod
    def parse(cls, raw: list[dict[str, str]]) -> ChatTranscript:
        """Boundary. Reject unknown roles and missing content."""
        if not isinstance(raw, list) or not raw:
            raise EngineError(EngineErrorCode.PROTOCOL, "transcript must be a non-empty list")
        parsed: list[ChatMessage] = []
        for row in raw:
            if not isinstance(row, dict):
                raise EngineError(EngineErrorCode.PROTOCOL, "each message must be a dict")
            try:
                role = Role(str(row.get("role", "")))
            except ValueError:
                raise EngineError(
                    EngineErrorCode.PROTOCOL,
                    f"unknown role: {row.get('role')!r}",
                ) from None
            content = _message_content(row)
            parsed.append(ChatMessage(role=role, content=content))
        return cls(messages=tuple(parsed))

    def split_for_agent(self) -> tuple[tuple[ChatMessage, ...], UserUtterance]:
        """Prior messages plus the trailing user utterance.

        Illegal when the last role is not USER.
        """
        if not self.messages or self.messages[-1].role is not Role.USER:
            raise EngineError(
                EngineErrorCode.NO_USER_UTTERANCE,
                "last message must be a user utterance",
            )
        return self.messages[:-1], UserUtterance(self.messages[-1].content)


def _message_content(row: dict[str, str]) -> str:
    model_content = row.get("model_content")
    if model_content:
        if not isinstance(model_content, str):
            raise EngineError(EngineErrorCode.PROTOCOL, "missing content")
        return model_content
    if "content" not in row or row["content"] is None:
        raise EngineError(EngineErrorCode.PROTOCOL, "missing content")
    content = row["content"]
    if not isinstance(content, str):
        raise EngineError(EngineErrorCode.PROTOCOL, "missing content")
    return content


class CancelToken:
    """Cross-thread cancel flag. The QThread owns the instance. The engine only reads."""

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def cancelled(self) -> bool:
        return self._cancelled


@dataclass(frozen=True)
class StatelessTurn:
    transcript: ChatTranscript
    model: HermesInferenceTarget
    cancel: CancelToken


@dataclass(frozen=True)
class ContentDelta:
    text: str


@dataclass(frozen=True)
class ToolProgress:
    label: str


@dataclass(frozen=True)
class TurnFinished:
    text: str


@dataclass(frozen=True)
class TurnFailed:
    error: EngineError


@dataclass(frozen=True)
class TurnCancelled:
    pass


TurnEvent = Union[ContentDelta, ToolProgress, TurnFinished, TurnFailed, TurnCancelled]


EngineHome = NewType("EngineHome", Path)
# Directory IRIS owns. Default ~/.iris-light/engine. Not %LOCALAPPDATA%\\hermes.

HermesHome = NewType("HermesHome", Path)
EnginePython = NewType("EnginePython", Path)
GuiPython = NewType("GuiPython", Path)


@dataclass(frozen=True)
class InternalSidecar:
    """Default source. shutdown() kills the child."""

    home: EngineHome
    kill_on_shutdown: Literal[True] = True


@dataclass(frozen=True)
class ExternalGateway:
    """Compatibility only. shutdown() disconnects and does not kill."""

    base_url: str
    api_key: str
    kill_on_shutdown: Literal[False] = False


EngineSource = Union[InternalSidecar, ExternalGateway]


def _default_engine_home() -> EngineHome:
    return EngineHome(Path.home() / ".iris-light" / "engine")


def _settings_flag(settings: object, name: str) -> bool:
    value = getattr(settings, name, False)
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no"}
    return bool(value)


def parse_engine_source(settings: object) -> EngineSource:
    """Settings boundary. Default InternalSidecar.

    ExternalGateway only when settings.hermes_external_gateway is true.
    hermes_enabled stays the 'use the engine' flag. It does not mean ':8642 is up'.
    """
    if _settings_flag(settings, "hermes_external_gateway"):
        return ExternalGateway(
            base_url=str(getattr(settings, "hermes_base_url", "") or ""),
            api_key=str(getattr(settings, "hermes_api_key", "") or ""),
        )
    return InternalSidecar(home=_default_engine_home())


@dataclass(frozen=True)
class EngineReady:
    source: EngineSource
    summary: str


@dataclass(frozen=True)
class EngineFailed:
    error: EngineError

    @property
    def user_message(self) -> str:
        return self.error.user_message


EngineEnsureResult = Union[EngineReady, EngineFailed]


IRIS_ENGINE_TOOLS = ("iris_get_state", "iris_get_catalog", "iris_invoke")

DANGEROUS_ACTIONS = frozenset(
    {
        "project.write_file",
        "project.run",
        "project.rename_file",
        "project.create_scaffold",
    }
)


def assert_iris_engine_tools_catalog(tools: tuple[str, ...] | None = None) -> None:
    """Boot check. Engine-facing tool names stay one unique list."""
    names = IRIS_ENGINE_TOOLS if tools is None else tools
    if len(names) != len(set(names)):
        raise AssertionError("IRIS_ENGINE_TOOLS has duplicate names")


def assert_dangerous_actions_confirm(registry: object) -> None:
    """Boot check. A registered DANGEROUS_ACTIONS name must have confirm_required."""
    spec_of = getattr(registry, "spec", None)
    if not callable(spec_of):
        raise AssertionError("registry has no spec()")
    missing: list[str] = []
    for name in sorted(DANGEROUS_ACTIONS):
        spec = spec_of(name)
        if spec is None or not getattr(spec, "confirm_required", False):
            missing.append(name)
    if missing:
        raise AssertionError(
            "DANGEROUS_ACTIONS missing confirm_required: " + ", ".join(missing)
        )


assert_iris_engine_tools_catalog()
