"""모델 자동 전환 — 실패 분류·백오프·전환 체인.

claude-code-router(MIT)의 세 파일을 옮긴 것이다.

- `routing/failure-classifier.ts` → `classify_failure`
- `gateway/upstream/retry-policy.ts` → `retry_delay_after_status` / `..._network_error`
- `routing/execution-plan.ts` → `build_execution_plan`

거기서 보고된 결함 둘은 피해서 옮겼다.

- #1804/#1831 — 체인이 죽은 provider로 계속 쏘던 문제. 여기서는 시도마다
  모델뿐 아니라 **백엔드(ollama/hermes/api provider)까지** 통째로 바꾼다.
- #1615 — 프로토콜이 바뀌었는데 body를 다시 안 만들던 문제. `RouteAttempt` 가
  백엔드를 들고 있어 호출부가 매 시도마다 요청을 새로 조립하게 강제한다.

여기에 CCR에 없는 것을 하나 더한다: 실패를 기다리지 않고 **할당량 잔량으로 미리**
갈아타는 판단(`should_preempt`). Ollama 주간 한도처럼 소진되면 429가 아니라 그냥
막히는 경우가 있어서다.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

MODE_OFF = "off"
MODE_RETRY = "retry"
MODE_MODEL_CHAIN = "model-chain"
MODES: tuple[str, ...] = (MODE_OFF, MODE_RETRY, MODE_MODEL_CHAIN)

CLASS_CLIENT = "client"
CLASS_RATE_LIMIT = "rate-limit"
CLASS_RETRYABLE = "retryable"
CLASS_SERVER = "server"

MAX_RETRY_COUNT = 9999
_BACKOFF_BASE_MS = 1_000
_BACKOFF_MAX_MS = 30_000
_RETRY_AFTER_MAX_MS = 60_000

# 이 비율을 넘으면 실패를 기다리지 않고 먼저 무료 모델로 내려간다.
DEFAULT_PREEMPT_PERCENT = 95.0


@dataclass(frozen=True)
class FailureDecision:
    failure_class: str
    should_fallback: bool

    @property
    def reason(self) -> str:
        return {
            CLASS_RATE_LIMIT: "할당량 소진",
            CLASS_RETRYABLE: "일시적 오류",
            CLASS_SERVER: "서버 오류",
            CLASS_CLIENT: "요청 오류",
        }.get(self.failure_class, self.failure_class)


def classify_status(status_code: int) -> str:
    code = int(status_code or 0)
    if code == 429:
        return CLASS_RATE_LIMIT
    if code in (408, 409):
        return CLASS_RETRYABLE
    if code >= 500:
        return CLASS_SERVER
    return CLASS_CLIENT


def classify_failure(status_code: int, mode: str = MODE_MODEL_CHAIN) -> FailureDecision:
    """HTTP 상태 → 전환할지 판단.

    `model-chain` 은 4xx 전부를 전환 사유로 본다. 모델이 달라지면 400(미지원
    파라미터)·401(키 없음)·404(모델 없음)도 다음 후보에서 풀릴 수 있기 때문이다.
    """
    failure_class = classify_status(status_code)
    if normalize_mode(mode) == MODE_MODEL_CHAIN:
        should = int(status_code or 0) >= 400
    else:
        should = failure_class in (CLASS_RETRYABLE, CLASS_RATE_LIMIT, CLASS_SERVER)
    return FailureDecision(failure_class=failure_class, should_fallback=should)


_HTTP_STATUS_RE = re.compile(r"\bHTTP[ /]?(?:1\.[01] )?(\d{3})\b", re.IGNORECASE)
# 상태 코드 없이 문구로만 오는 한도 초과 — Ollama·OpenAI 호환 게이트웨이 공통
_RATE_LIMIT_HINTS = (
    "rate limit",
    "rate_limit",
    "too many requests",
    "quota",
    "exceeded your current",
    "insufficient_quota",
    "한도",
    "할당량",
)
_UNREACHABLE_HINTS = ("연결 실패", "connection refused", "timed out", "timeout", "unreachable")


def parse_http_status(message: str) -> int:
    """오류 문자열에서 HTTP 상태를 뽑는다. 못 찾으면 0."""
    match = _HTTP_STATUS_RE.search(str(message or ""))
    return int(match.group(1)) if match else 0


def status_for_error(message: str) -> int:
    """예외 문구 → 전환 판단에 쓸 상태 코드.

    Ollama 클라이언트는 예외를 문자열로만 올려준다. 상태가 안 박혀 있으면
    문구로 한도 초과·연결 불가를 갈라낸다 — 둘 다 다음 후보로 넘어갈 사유다.
    """
    status = parse_http_status(message)
    if status:
        return status
    text = str(message or "").lower()
    if any(hint in text for hint in _RATE_LIMIT_HINTS):
        return 429
    if any(hint in text for hint in _UNREACHABLE_HINTS):
        return 503
    return 0


def normalize_mode(mode: str) -> str:
    value = (mode or "").strip().lower()
    return value if value in MODES else MODE_MODEL_CHAIN


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def _exponential_backoff_ms(failed_attempt_index: int) -> int:
    exponent = int(_clamp(int(failed_attempt_index or 0), 0, 10))
    return int(min(_BACKOFF_MAX_MS, _BACKOFF_BASE_MS * (2**exponent)))


def parse_retry_after_ms(value: str | None) -> int | None:
    """`Retry-After` — 초 단위 숫자 또는 HTTP 날짜."""
    text = (value or "").strip()
    if not text:
        return None
    try:
        seconds = float(text)
        if seconds >= 0:
            return int(seconds * 1000)
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    delta_ms = (when - datetime.now(timezone.utc)).total_seconds() * 1000
    return int(max(0.0, delta_ms))


def retry_delay_after_status(retry_after: str | None, failed_attempt_index: int = 0) -> int:
    """서버가 알려준 대기시간 우선, 없으면 지수 백오프 (ms)."""
    hinted = parse_retry_after_ms(retry_after)
    if hinted is not None and hinted > 0:
        return int(_clamp(hinted, 1, _RETRY_AFTER_MAX_MS))
    return _exponential_backoff_ms(failed_attempt_index)


def retry_delay_after_network_error(failed_attempt_index: int = 0) -> int:
    return _exponential_backoff_ms(failed_attempt_index)


@dataclass(frozen=True)
class RouteTarget:
    """전환 후보 하나. 모델만이 아니라 어느 백엔드로 갈지까지 들고 있다."""

    model: str
    backend: str = ""  # ollama | agent | api | ''(현재 것 유지); legacy hermes ok
    label: str = ""
    free: bool = False

    def __post_init__(self) -> None:
        if not self.label:
            object.__setattr__(self, "label", self.model)

    @property
    def key(self) -> str:
        return f"{self.backend}|{self.model}"


class RouteCooldownBook:
    """Rate-limit 뒤 해당 RouteTarget 을 until_monotonic 까지 체인에서 건너뛴다."""

    def __init__(self) -> None:
        self._until: dict[str, float] = {}

    def mark_cool(self, target: RouteTarget, until_monotonic: float) -> None:
        self._until[target.key] = max(
            self._until.get(target.key, 0.0), float(until_monotonic)
        )

    def is_cool(
        self, target: RouteTarget, now_monotonic: float | None = None
    ) -> bool:
        now = time.monotonic() if now_monotonic is None else float(now_monotonic)
        until = self._until.get(target.key)
        return until is not None and now < until

    def filter_ready(
        self,
        targets: list[RouteTarget],
        now_monotonic: float | None = None,
    ) -> list[RouteTarget]:
        return [t for t in targets if not self.is_cool(t, now_monotonic)]


@dataclass(frozen=True)
class RouteAttempt:
    index: int
    target: RouteTarget
    is_primary: bool


@dataclass(frozen=True)
class ExecutionPlan:
    attempts: list[RouteAttempt] = field(default_factory=list)
    mode: str = MODE_MODEL_CHAIN
    primary: RouteTarget | None = None

    def next_after(self, index: int) -> RouteAttempt | None:
        nxt = index + 1
        return self.attempts[nxt] if 0 <= nxt < len(self.attempts) else None

    @property
    def has_fallback(self) -> bool:
        return len(self.attempts) > 1


def build_execution_plan(
    primary: RouteTarget | None,
    fallbacks: list[RouteTarget] | None = None,
    *,
    mode: str = MODE_MODEL_CHAIN,
    retry_count: int = 2,
) -> ExecutionPlan:
    """전환 체인을 시도 배열로 펼친다."""
    mode_value = normalize_mode(mode)
    if primary is None:
        return ExecutionPlan(attempts=[], mode=mode_value, primary=None)

    if mode_value == MODE_OFF:
        return ExecutionPlan(
            attempts=[RouteAttempt(index=0, target=primary, is_primary=True)],
            mode=mode_value,
            primary=primary,
        )

    if mode_value == MODE_RETRY:
        count = int(_clamp(int(retry_count or 0), 0, MAX_RETRY_COUNT))
        return ExecutionPlan(
            attempts=[
                RouteAttempt(index=i, target=primary, is_primary=True)
                for i in range(count + 1)
            ],
            mode=mode_value,
            primary=primary,
        )

    seen: set[str] = set()
    ordered: list[RouteTarget] = []
    for target in [primary, *(fallbacks or [])]:
        if target is None or not (target.model or "").strip():
            continue
        if target.key in seen:
            continue
        seen.add(target.key)
        ordered.append(target)
    return ExecutionPlan(
        attempts=[
            RouteAttempt(index=i, target=t, is_primary=(i == 0))
            for i, t in enumerate(ordered)
        ],
        mode=mode_value,
        primary=primary,
    )


def should_preempt(
    quotas: list[object],
    *,
    threshold_percent: float = DEFAULT_PREEMPT_PERCENT,
    keys: tuple[str, ...] = ("sess", "week"),
) -> tuple[bool, str]:
    """`api_quota.fetch_api_quotas()` 결과로 미리 갈아탈지 판단.

    반환: (전환할까, 사유). 429가 오기 전에 내려가려는 것이라 실패 판정과 별개다.
    """
    limit = float(threshold_percent)
    for quota in quotas or []:
        key = str(getattr(quota, "key", "") or "")
        if keys and key not in keys:
            continue
        try:
            percent = float(getattr(quota, "percent", 0.0))
        except (TypeError, ValueError):
            continue
        if percent >= limit:
            label = str(getattr(quota, "label", "") or key)
            return True, f"{label} 사용률 {percent:.0f}% — 한도 임박"
    return False, ""


def describe_switch(frm: RouteTarget | None, to: RouteTarget, reason: str) -> str:
    """채팅에 띄울 전환 안내 한 줄."""
    src = frm.label if frm else "이전 모델"
    tail = " (무료)" if to.free else ""
    base = f"{src} → {to.label}{tail} 로 전환했습니다"
    return f"{base} — {reason}." if reason else f"{base}."


if __name__ == "__main__":
    assert classify_status(429) == CLASS_RATE_LIMIT
    assert classify_status(408) == CLASS_RETRYABLE and classify_status(409) == CLASS_RETRYABLE
    assert classify_status(503) == CLASS_SERVER
    assert classify_status(400) == CLASS_CLIENT and classify_status(404) == CLASS_CLIENT

    # model-chain 은 4xx 전부 전환, retry 모드는 클라이언트 오류를 붙잡지 않는다
    assert classify_failure(400, MODE_MODEL_CHAIN).should_fallback is True
    assert classify_failure(400, MODE_RETRY).should_fallback is False
    assert classify_failure(429, MODE_RETRY).should_fallback is True
    assert classify_failure(500, MODE_RETRY).should_fallback is True
    assert classify_failure(429, MODE_MODEL_CHAIN).reason == "할당량 소진"
    assert normalize_mode("이상한값") == MODE_MODEL_CHAIN
    assert normalize_mode("OFF") == MODE_OFF

    assert parse_retry_after_ms("2") == 2000
    assert parse_retry_after_ms("0") == 0
    assert parse_retry_after_ms("") is None
    assert parse_retry_after_ms("쓰레기") is None
    assert parse_retry_after_ms("Wed, 21 Oct 2015 07:28:00 GMT") == 0  # 과거 → 0
    assert retry_delay_after_status("5") == 5000
    assert retry_delay_after_status("99999") == _RETRY_AFTER_MAX_MS  # 상한
    assert retry_delay_after_status(None, 0) == 1000
    assert retry_delay_after_status(None, 3) == 8000
    assert retry_delay_after_status(None, 99) == _BACKOFF_MAX_MS
    assert retry_delay_after_network_error(1) == 2000

    primary = RouteTarget(model="qwen3:8b", backend="ollama", label="qwen3 8b")
    free1 = RouteTarget(model="gemma4:free", backend="ollama", free=True)
    free2 = RouteTarget(model="llama4:free", backend="api", free=True)

    plan = build_execution_plan(primary, [free1, free2])
    assert [a.target.model for a in plan.attempts] == ["qwen3:8b", "gemma4:free", "llama4:free"]
    assert plan.attempts[0].is_primary is True and plan.attempts[1].is_primary is False
    assert plan.has_fallback is True
    assert plan.next_after(0).target.model == "gemma4:free"
    assert plan.next_after(2) is None

    # 같은 모델이라도 백엔드가 다르면 별개 후보다 (#1804 회피)
    dup = build_execution_plan(primary, [RouteTarget(model="qwen3:8b", backend="agent"), free1])
    assert len(dup.attempts) == 3
    same = build_execution_plan(primary, [RouteTarget(model="qwen3:8b", backend="ollama")])
    assert len(same.attempts) == 1

    off = build_execution_plan(primary, [free1], mode=MODE_OFF)
    assert len(off.attempts) == 1 and off.has_fallback is False
    retry = build_execution_plan(primary, [free1], mode=MODE_RETRY, retry_count=3)
    assert len(retry.attempts) == 4
    assert all(a.target.model == "qwen3:8b" for a in retry.attempts)
    assert build_execution_plan(None, [free1]).attempts == []
    assert build_execution_plan(primary, [RouteTarget(model="  ")]).attempts == [
        RouteAttempt(index=0, target=primary, is_primary=True)
    ]

    class _Q:
        def __init__(self, key, label, percent):
            self.key, self.label, self.percent = key, label, percent

    hit, why = should_preempt([_Q("week", "WEEK", 97.0)])
    assert hit is True and "97%" in why
    assert should_preempt([_Q("week", "WEEK", 50.0)])[0] is False
    assert should_preempt([])[0] is False
    assert should_preempt([_Q("serp", "SERP", 99.0)])[0] is False  # 채팅과 무관한 할당량
    assert should_preempt([_Q("sess", "SESS", 96.0)], threshold_percent=99.0)[0] is False

    assert parse_http_status("Ollama HTTP 429: slow down") == 429
    assert parse_http_status("HTTP/1.1 503 Service Unavailable") == 503
    assert parse_http_status("그냥 오류") == 0
    assert status_for_error("Ollama HTTP 404: model not found") == 404
    assert status_for_error("You exceeded your current quota") == 429
    assert status_for_error("rate limit reached") == 429
    assert status_for_error("주간 할당량을 다 썼습니다") == 429
    assert status_for_error("Ollama 연결 실패: [WinError 10061]") == 503
    assert status_for_error("알 수 없는 문제") == 0
    # 상태가 없어 0이면 전환하지 않는다 — 원인을 모르는 채 모델만 바꾸면 안 된다
    assert classify_failure(0, MODE_MODEL_CHAIN).should_fallback is False

    assert "무료" in describe_switch(primary, free1, "할당량 소진")
    assert describe_switch(None, free1, "").endswith("전환했습니다.")

    book = RouteCooldownBook()
    cool_t = RouteTarget(model="cool", backend="api")
    hot_t = RouteTarget(model="hot", backend="api")
    assert book.is_cool(cool_t) is False
    book.mark_cool(cool_t, until_monotonic=1.0)
    assert book.is_cool(cool_t, now_monotonic=0.5) is True
    assert book.is_cool(cool_t, now_monotonic=1.5) is False
    assert [t.model for t in book.filter_ready([cool_t, hot_t], now_monotonic=0.5)] == [
        "hot"
    ]
    print("model_failover self-check ok")
