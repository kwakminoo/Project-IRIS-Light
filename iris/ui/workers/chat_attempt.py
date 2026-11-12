"""채팅 전환 체인의 공용 부품 — Ollama·Hermes 워커가 같이 쓴다.

워커는 DB도 위키도 만지지 않는다. 후보마다 **그 후보에게 보낼 messages**(와
Hermes라면 해석된 타깃)를 UI 스레드가 미리 만들어 여기 담아 넘긴다.

claude-code-router 이슈 #1615(프로토콜이 바뀌었는데 body를 재사용해 400이 나던
문제)를 피하려는 구조다. 후보가 자기 요청을 통째로 들고 있으면 재사용할 수가 없다.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from iris.runtime.model_failover import (
    CLASS_RATE_LIMIT,
    RouteTarget,
    classify_failure,
    retry_delay_after_status,
    status_for_error,
)


@dataclass
class ChatAttempt:
    """전환 체인의 한 칸."""

    model: str
    messages: list[dict[str, str]] = field(default_factory=list)
    label: str = ""
    free: bool = False
    reason_hint: str = ""
    # Hermes 전용 — resolve_iris_agent_inference() 결과. UI 스레드에서 미리 푼다.
    target: Any = None
    route_target: RouteTarget | None = None

    def __post_init__(self) -> None:
        self.model = str(self.model or "")
        self.label = str(self.label or "") or self.model


@dataclass(frozen=True)
class ApiCall:
    """커스텀 OpenAI 호환 후보의 호출 정보.

    후보마다 프로바이더가 다를 수 있어 base_url·키까지 후보가 들고 있어야 한다.
    `ChatAttempt.target` 에 담아 넘긴다.
    """

    base_url: str
    api_key: str
    model: str  # 업스트림 모델명 (IRIS 런타임 id 가 아니다)
    auth_style: str = "bearer"


@dataclass(frozen=True)
class FallbackStep:
    """다음 후보로 넘어가기로 한 결정."""

    reason: str
    delay_ms: int
    status: int
    cool_until_monotonic: float | None = None


def decide_fallback(
    error: str,
    failed_attempt_index: int,
    *,
    retry_after: str | None = None,
    now_monotonic: float | None = None,
) -> FallbackStep | None:
    """실패 문구를 보고 다음 후보로 넘어갈지 정한다. 안 넘어가면 None.

    원인을 못 읽은 실패(status 0)는 넘어가지 않는다 — 이유도 모른 채 모델만
    바꾸면 사용자는 왜 답이 달라졌는지 알 수 없다.
    """
    status = status_for_error(error)
    if not status:
        return None
    decision = classify_failure(status)
    if not decision.should_fallback:
        return None
    delay_ms = retry_delay_after_status(retry_after, failed_attempt_index)
    return FallbackStep(
        reason=decision.reason,
        delay_ms=delay_ms,
        status=status,
        cool_until_monotonic=(
            (time.monotonic() if now_monotonic is None else float(now_monotonic))
            + delay_ms / 1000.0
            if decision.failure_class == CLASS_RATE_LIMIT
            else None
        ),
    )


def normalize_attempts(
    attempts: list[ChatAttempt] | None,
    *,
    model: str,
    messages: list[dict[str, str]],
) -> list[ChatAttempt]:
    """후보를 안 넘긴 기존 호출부도 그대로 돌아가게 한다."""
    items = [a for a in (attempts or []) if (a.model or "").strip()]
    return items or [ChatAttempt(model, messages)]


def route_target_for_attempt(attempt: ChatAttempt, backend: str) -> RouteTarget:
    return attempt.route_target or RouteTarget(
        model=attempt.model,
        backend=backend,
        label=attempt.label,
        free=attempt.free,
    )


if __name__ == "__main__":
    a = ChatAttempt("m", [{"role": "user", "content": "x"}])
    assert a.label == "m" and a.target is None and a.free is False
    assert ChatAttempt("m", label="예쁜 이름").label == "예쁜 이름"

    step = decide_fallback("Ollama HTTP 429: rate limit", 0)
    assert step is not None and step.reason == "할당량 소진" and step.delay_ms == 1000
    assert decide_fallback("Hermes HTTP 503: upstream", 2).delay_ms == 4000
    assert decide_fallback("You exceeded your current quota", 0).status == 429
    assert decide_fallback("Iris Agent 연결 실패: refused", 0).status == 503
    # 원인을 모르면 넘어가지 않는다
    assert decide_fallback("알 수 없는 문제", 0) is None
    assert decide_fallback("", 0) is None

    solo = normalize_attempts(None, model="m", messages=[{"role": "user", "content": "q"}])
    assert len(solo) == 1 and solo[0].model == "m"
    assert normalize_attempts([ChatAttempt("  ")], model="m", messages=[])[0].model == "m"
    chain = normalize_attempts(
        [ChatAttempt("a"), ChatAttempt("b")], model="m", messages=[]
    )
    assert [c.model for c in chain] == ["a", "b"]
    call = ApiCall(base_url="https://x/v1", api_key="k", model="gpt-x")
    assert call.auth_style == "bearer"
    holder = ChatAttempt("api:ab:gpt-x", target=call)
    assert holder.target.model == "gpt-x" and holder.model == "api:ab:gpt-x"
    print("chat_attempt self-check ok")
