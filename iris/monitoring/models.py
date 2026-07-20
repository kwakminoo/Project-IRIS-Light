"""모니터링 도메인 모델 (원본 스크린샷·전체 OCR 원문은 DB에 저장하지 않음)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class TargetType(str, Enum):
    """모니터링 대상 유형."""

    CURRENT_SCREEN = "current_screen"
    DESKTOP_WINDOW = "desktop_window"
    BROWSER_TAB = "browser_tab"
    TERMINAL_COMMAND = "terminal_command"
    SYSTEM_LOG = "system_log"


class StatusCategory(str, Enum):
    """상태 분류."""

    NORMAL = "NORMAL"
    APPROVAL_WAITING = "APPROVAL_WAITING"
    ERROR_DETECTED = "ERROR_DETECTED"
    GENERATION_FAILED = "GENERATION_FAILED"
    TASK_STALLED = "TASK_STALLED"
    RESPONSE_READY = "RESPONSE_READY"
    BUILD_NOT_STARTED = "BUILD_NOT_STARTED"
    USER_ACTION_REQUIRED = "USER_ACTION_REQUIRED"
    UNKNOWN = "UNKNOWN"


@dataclass
class MonitoredTarget:
    """등록된 모니터링 대상 (메모리/DB 공통)."""

    id: int | None
    type: TargetType
    title: str
    process_name: str = ""
    url: str = ""
    handle: str = ""  # HWND 문자열 등
    enabled: bool = True
    status: StatusCategory = StatusCategory.UNKNOWN
    last_checked_at: datetime | None = None
    last_event: str = ""
    created_at: datetime | None = None


@dataclass
class DetectionResult:
    """state_detector 출력."""

    category: StatusCategory
    confidence: float
    reason: str
    recommended_action: str


@dataclass
class CollectedSnippet:
    """수집된 텍스트 스니펫 (DB에는 해시·요약만 권장)."""

    text: str
    source: str = ""
    meta: dict[str, Any] = field(default_factory=dict)
