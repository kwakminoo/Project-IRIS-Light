from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal, NewType, Union

from iris.infrastructure.iris_agent_client import IrisAgentInferenceTarget
from iris.infrastructure.speak_capability import (
    PHASE4_ALLOWLIST,
    SpeakSurface,
    assert_engine_tools_match_allowlist,
)


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
    TURN_IDLE = "turn_idle"
    AUTH = "auth"
    CANCELLED = "cancelled"
    NO_USER_UTTERANCE = "no_user_utterance"
    TOOL_TRANSPORT = "tool_transport"
    TOOL_ERROR_BUDGET = "tool_error_budget"
    BILLING = "billing"
    UNKNOWN = "unknown"


_USER_MESSAGES = {
    EngineErrorCode.NOT_INSTALLED: "엔진이 아직 설치되지 않았습니다.",
    EngineErrorCode.WRONG_PYTHON: "엔진 Python이 IRIS와 다릅니다.",
    EngineErrorCode.SPAWN_FAILED: "엔진을 시작하지 못했습니다.",
    EngineErrorCode.SIDECAR_DIED: "엔진 프로세스가 종료되었습니다.",
    EngineErrorCode.PROTOCOL: "엔진 응답을 읽지 못했습니다.",
    EngineErrorCode.TURN_IDLE: "응답 대기 시간이 초과됐습니다. 잠시 후 다시 시도하세요.",
    EngineErrorCode.AUTH: "엔진 인증에 실패했습니다.",
    EngineErrorCode.CANCELLED: "요청이 취소되었습니다.",
    EngineErrorCode.NO_USER_UTTERANCE: "보낼 사용자 메시지가 없습니다.",
    EngineErrorCode.TOOL_TRANSPORT: "도구 호출에 실패했습니다.",
    EngineErrorCode.TOOL_ERROR_BUDGET: "도구 오류가 안전 제한을 넘어 작업을 중단했습니다.",
    EngineErrorCode.BILLING: (
        "Ollama 클라우드 크레딧이 부족합니다. "
        "요금을 충전하거나 다른 모델로 바꾸세요."
    ),
    EngineErrorCode.UNKNOWN: "엔진에서 알 수 없는 오류가 났습니다.",
}


def engine_user_messages() -> frozenset[str]:
    """Chat UI strings already authored for EngineErrorCode. Pass through explain_chat_error."""
    return frozenset(_USER_MESSAGES.values())


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
    model: IrisAgentInferenceTarget
    cancel: CancelToken
    speak_surface: SpeakSurface = "home"


@dataclass(frozen=True)
class ContentDelta:
    text: str


@dataclass(frozen=True)
class ToolProgress:
    label: str


@dataclass(frozen=True)
class AppUiOfferEvent:
    title: str
    html_path: str  # local filesystem path for Phase 2
    resource_uri: str = ""  # optional raw _meta.ui.resourceUri for later


@dataclass(frozen=True)
class ReasoningDelta:
    text: str


@dataclass(frozen=True)
class TurnFinished:
    text: str


@dataclass(frozen=True)
class TurnFailed:
    error: EngineError


@dataclass(frozen=True)
class TurnCancelled:
    pass


TurnEvent = Union[
    ContentDelta,
    ToolProgress,
    AppUiOfferEvent,
    ReasoningDelta,
    TurnFinished,
    TurnFailed,
    TurnCancelled,
]


EngineHome = NewType("EngineHome", Path)
# Directory IRIS owns. Default iris_agent_home() (~/.iris-light/agent).

HermesHome = NewType("HermesHome", Path)
EnginePython = NewType("EnginePython", Path)
GuiPython = NewType("GuiPython", Path)


@dataclass(frozen=True)
class InternalSidecar:
    """Product source. shutdown() kills the child."""

    home: EngineHome
    kill_on_shutdown: Literal[True] = True


# Unit 2: product EngineSource is sidecar-only (HTTP gateway union arm removed).
EngineSource = InternalSidecar


def _default_engine_home() -> EngineHome:
    # Product home (= Iris Agent home). Same tree as pin/migrate/supervisor.
    from iris.infrastructure.agent_runtime import iris_agent_home

    return EngineHome(iris_agent_home())


def parse_engine_source(settings: object) -> EngineSource:
    """Settings boundary. Product path is always InternalSidecar.

    agent_enabled (alias hermes_enabled) is the 'use the engine' flag.
    It does not mean ':8642 is up'. hermes_external_gateway / IRIS_HERMES_EXTERNAL_GATEWAY
    no longer select a product source.
    """
    _ = settings
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


# Product engine catalog == SpeakTools allowlist (not MCP iris-control triple).
IRIS_ENGINE_TOOLS = PHASE4_ALLOWLIST.names()

DANGEROUS_ACTIONS = frozenset(
    {
        "project.write_file",
        "project.run",
        "project.rename_file",
        "project.create_scaffold",
    }
)


def assert_iris_engine_tools_catalog(tools: tuple[str, ...] | None = None) -> None:
    """Boot check. Engine-facing tool names stay one unique SpeakTools list."""
    names = IRIS_ENGINE_TOOLS if tools is None else tools
    if len(names) != len(set(names)):
        raise AssertionError("IRIS_ENGINE_TOOLS has duplicate names")
    mcp_triple = ("iris_get_state", "iris_get_catalog", "iris_invoke")
    if tuple(names) == mcp_triple:
        raise AssertionError("IRIS_ENGINE_TOOLS must not be the MCP triple")
    assert_engine_tools_match_allowlist(tuple(names))


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
