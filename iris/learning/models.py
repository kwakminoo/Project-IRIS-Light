"""학습 도메인 모델 — Aloha field는 adapter에서만 직렬화."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LearningState(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"
    ERROR = "error"


@dataclass
class LearningEvent:
    """IRIS 정규화 이벤트 (Aloha NDJSON과 분리)."""

    timestamp: float
    event_type: str
    x: float | None = None
    y: float | None = None
    key: str | None = None
    text: str | None = None
    modifiers: tuple[str, ...] = ()
    window_title: str = ""
    process_name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    # learning control 자체 클릭 등 — trace에서 제외
    exclude_from_trace: bool = False


@dataclass
class SessionManifest:
    session_id: str
    started_at: str
    ended_at: str = ""
    status: str = "recording"  # recording|finalized|processing|ready|failed|interrupted|pending_vlm
    screen_width: int = 0
    screen_height: int = 0
    scale_factor: float = 1.0
    fps: float = 4.0
    event_count: int = 0
    video_path: str = ""
    events_path: str = ""
    aloha_log_path: str = ""
    trace_path: str = ""
    error: str = ""
    iris_hwnds: list[int] = field(default_factory=list)


@dataclass
class TraceStep:
    """Aloha caption을 IRIS 쪽에서 감싼 형태."""

    step_idx: int
    observation: str = ""
    think: str = ""
    action: str = ""
    expectation: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class SemanticTrace:
    trace_id: str
    steps: list[TraceStep] = field(default_factory=list)
    path: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class LearnedWorkflow:
    id: int
    trace_id: str
    name: str
    summary: str
    status: str
    source_session_id: str
    trace_path: str
    primary_apps: str
    created_at: str
    updated_at: str
    last_run_at: str = ""
    run_count: int = 0
    enabled: int = 1


@dataclass
class WorkflowRun:
    run_id: str
    workflow_id: int
    trace_id: str
    task: str
    status: str  # queued|running|succeeded|failed|cancelled
    message: str = ""
    started_at: str = ""
    finished_at: str = ""
