"""상황별 음성 명령 — 규칙 기반 인텐트 매칭.

전화가 울리는 동안 "전화 받아줘" 같은 짧은 말은 **모델을 거치지 않고** 바로
처리한다. 이유는 두 가지다.

1. **속도** — 전화벨은 몇 초 만에 끊긴다. LLM 왕복(수 초)을 기다릴 여유가 없다.
   여기서 매칭되면 STT가 끝난 그 프레임에 바로 adb 명령이 나간다.
2. **예측 가능성** — 전화를 받는 건 되돌릴 수 없는 동작이다. 모델의 그날 기분에
   맡기지 않고 규칙으로 고정한다.

사용자가 인지 상태나 발음 문제로 정확히 말하지 못할 수 있으므로, 매칭은
**느슨하게** 잡는다(조사·띄어쓰기 무시, 부분 일치, 자모 유사도 폴백).
대신 되돌릴 수 없는 인텐트는 `context` 로 상황을 좁혀 오탐을 막는다 —
전화가 안 울리는데 "받아줘"라고 해서 뭔가 받아지면 안 된다.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum


class VoiceIntent(str, Enum):
    """규칙으로 처리하는 상황별 명령."""

    ANSWER_CALL = "answer_call"
    REJECT_CALL = "reject_call"
    HANG_UP = "hang_up"
    READ_ALERT = "read_alert"
    REPEAT_ALERT = "repeat_alert"
    SILENCE_ALERT = "silence_alert"


class IntentContext(str, Enum):
    """지금 화면/기기 상태. 되돌릴 수 없는 인텐트를 좁히는 데 쓴다."""

    IDLE = "idle"
    CALL_RINGING = "call_ringing"
    CALL_ACTIVE = "call_active"
    ALERT_PENDING = "alert_pending"


# 인텐트별로 이 상황에서만 실행한다. 비어 있으면 언제나 허용.
_REQUIRED_CONTEXT: dict[VoiceIntent, tuple[IntentContext, ...]] = {
    VoiceIntent.ANSWER_CALL: (IntentContext.CALL_RINGING,),
    VoiceIntent.REJECT_CALL: (IntentContext.CALL_RINGING,),
    VoiceIntent.HANG_UP: (IntentContext.CALL_ACTIVE, IntentContext.CALL_RINGING),
    # 알림 관련도 상황을 좁힌다. "그만"·"다시"·"읽어줘"는 평소 대화에 너무 흔해서
    # 항상 열어 두면 일반 요청을 가로챈다.
    VoiceIntent.READ_ALERT: (IntentContext.ALERT_PENDING,),
    VoiceIntent.REPEAT_ALERT: (IntentContext.ALERT_PENDING,),
    VoiceIntent.SILENCE_ALERT: (IntentContext.ALERT_PENDING, IntentContext.CALL_RINGING),
}


@dataclass(frozen=True)
class IntentSpec:
    """한 인텐트의 매칭 규칙."""

    intent: VoiceIntent
    # UI에 그대로 보여 줄 대표 문장. 사용자가 따라 읽을 수 있어야 한다.
    prompt: str
    # 사람이 실제로 말할 법한 문장들. 부분 일치와 유사도 폴백의 기준.
    phrases: tuple[str, ...]
    # 이 낱말들이 다 들어 있으면 문장이 달라도 인정한다 (AND 묶음의 OR 목록).
    keyword_sets: tuple[tuple[str, ...], ...] = ()
    # 하나라도 있으면 매칭하지 않는다. 부정문·반대 동작 오탐 방지.
    blockers: tuple[str, ...] = ()


# ----------------------------------------------------------------------
# 상황별 문장 예시
#
# 발음이 흐리거나 문장이 잘려도 걸리도록, 짧은 변형을 넉넉히 넣는다.
# ----------------------------------------------------------------------

INTENT_SPECS: tuple[IntentSpec, ...] = (
    IntentSpec(
        intent=VoiceIntent.ANSWER_CALL,
        prompt="전화 받아줘",
        phrases=(
            "전화 받아줘",
            "전화 받아",
            "전화 받아주세요",
            "전화 좀 받아줘",
            "전화받아",
            "받아줘",
            "받아",
            "받아주세요",
            "통화 연결해줘",
            "연결해줘",
            "통화 시작",
            "받을게",
            "받겠습니다",
            "네 받아줘",
            "응 받아줘",
            "수신",
            "전화 연결",
            "콜 받아줘",
            "answer",
            "pick up",
        ),
        keyword_sets=(
            ("전화", "받"),
            ("통화", "연결"),
            ("전화", "연결"),
        ),
        blockers=("받지마", "받지 마", "받지말", "끊", "거절", "안받", "안 받"),
    ),
    IntentSpec(
        intent=VoiceIntent.REJECT_CALL,
        prompt="전화 끊어줘",
        phrases=(
            "전화 끊어줘",
            "끊어줘",
            "끊어",
            "거절해줘",
            "거절",
            "받지마",
            "받지 마",
            "받지 말아줘",
            "안 받을래",
            # "무시해줘"/"나중에"/"지금 안돼"는 뺐다. 전화를 끊는 건 되돌릴 수
            # 없는데, "무시해줘"는 "다시 해줘"와 자모 유사도 0.75로 붙어서
            # 평범한 말에 통화가 끊긴다.
            "reject",
            "decline",
        ),
        keyword_sets=(
            ("전화", "끊"),
            ("전화", "거절"),
        ),
        blockers=(),
    ),
    IntentSpec(
        intent=VoiceIntent.HANG_UP,
        prompt="통화 종료해줘",
        phrases=(
            "통화 종료",
            "통화 끝내줘",
            "통화 끊어줘",
            "이제 끊어줘",
            "그만 끊어",
            "종료해줘",
            "hang up",
        ),
        keyword_sets=(
            ("통화", "종료"),
            ("통화", "끊"),
            ("통화", "끝"),
        ),
        blockers=(),
    ),
    IntentSpec(
        intent=VoiceIntent.READ_ALERT,
        prompt="알림 읽어줘",
        phrases=(
            "알림 읽어줘",
            "읽어줘",
            "뭐라고 왔어",
            "무슨 알림이야",
            "알림 뭐야",
            "누구한테 왔어",
            "read it",
        ),
        keyword_sets=(
            ("알림", "읽"),
            ("메시지", "읽"),
            ("누구", "왔"),
        ),
        blockers=("읽지마", "읽지 마", "메일", "이메일", "일정", "캘린더"),
    ),
    IntentSpec(
        intent=VoiceIntent.REPEAT_ALERT,
        prompt="다시 말해줘",
        phrases=(
            "다시 말해줘",
            "다시",
            "한번 더",
            "한 번 더",
            "못 들었어",
            "다시 읽어줘",
            "뭐라고",
            "again",
        ),
        keyword_sets=(
            ("다시", "말"),
            ("다시", "읽"),
            ("한번", "더"),
        ),
        blockers=(),
    ),
    IntentSpec(
        intent=VoiceIntent.SILENCE_ALERT,
        prompt="알림 그만",
        phrases=(
            "알림 그만",
            "조용히",
            "조용히 해",
            "그만 말해",
            "음소거",
            "그만",
            "멈춰",
            "stop",
            "quiet",
        ),
        keyword_sets=(
            ("알림", "그만"),
            ("알림", "끄"),
        ),
        blockers=(),
    ),
)

_BY_INTENT: dict[VoiceIntent, IntentSpec] = {spec.intent: spec for spec in INTENT_SPECS}

# 자모 유사도 폴백 임계값. 낮추면 발음이 뭉개져도 잡히지만 오탐이 는다.
# 되돌릴 수 없는 인텐트는 아래 _STRICT_RATIO 를 따로 쓴다.
FUZZY_RATIO = 0.70
_STRICT_RATIO = 0.75
_STRICT_INTENTS = (VoiceIntent.ANSWER_CALL, VoiceIntent.REJECT_CALL, VoiceIntent.HANG_UP)

# 말끝 군더더기 — STT가 자주 붙이는 것들
_FILLERS = (
    "아이리스", "이리스", "iris", "야", "좀", "그", "저기", "음", "어",
    "please", "플리즈",
)
_PUNCT = re.compile(r"[^\w가-힣]+", re.UNICODE)


def normalize(text: str) -> str:
    """비교용 정규화 — 공백·문장부호·호출어를 지우고 소문자로."""
    body = unicodedata.normalize("NFKC", str(text or "")).strip().lower()
    if not body:
        return ""
    body = _PUNCT.sub(" ", body)
    for filler in _FILLERS:
        body = body.replace(filler, " ")
    return re.sub(r"\s+", "", body)


def _decompose(text: str) -> str:
    """한글 음절을 자모로 편다.

    발음 문제로 종성이 흐려지거나 STT가 비슷한 글자로 잘못 받아쓴 경우
    (예: "받아줘" → "바다줘"), 음절 단위 비교는 완전히 다른 문자열로 보지만
    자모 단위로 펴면 상당 부분이 겹친다.
    """
    out: list[str] = []
    for ch in text:
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:
            index = code - 0xAC00
            out.append(chr(0x1100 + index // 588))
            out.append(chr(0x1161 + (index % 588) // 28))
            jong = index % 28
            if jong:
                out.append(chr(0x11A7 + jong))
        else:
            out.append(ch)
    return "".join(out)


def similarity(left: str, right: str) -> float:
    """0.0~1.0. 자모로 편 뒤 비교해 발음이 흐려진 경우를 건진다."""
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    return SequenceMatcher(None, _decompose(left), _decompose(right)).ratio()


@dataclass
class IntentMatch:
    """매칭 결과."""

    intent: VoiceIntent
    confidence: float
    matched_phrase: str
    rule: str  # exact | contains | keywords | fuzzy
    text: str = ""
    spec: IntentSpec | None = field(default=None, repr=False)

    @property
    def prompt(self) -> str:
        return self.spec.prompt if self.spec else ""


def allowed_intents(context: IntentContext) -> tuple[VoiceIntent, ...]:
    """지금 상황에서 실행 가능한 인텐트."""
    out: list[VoiceIntent] = []
    for spec in INTENT_SPECS:
        required = _REQUIRED_CONTEXT.get(spec.intent, ())
        if not required or context in required:
            out.append(spec.intent)
    return tuple(out)


def prompts_for(context: IntentContext) -> tuple[str, ...]:
    """UI 힌트에 띄울 문장들 — 지금 말하면 통하는 것만."""
    return tuple(
        _BY_INTENT[intent].prompt
        for intent in allowed_intents(context)
        if intent in _BY_INTENT
    )


def _match_spec(spec: IntentSpec, body: str) -> IntentMatch | None:
    if not body:
        return None

    for blocker in spec.blockers:
        if normalize(blocker) and normalize(blocker) in body:
            return None

    candidates = [(phrase, normalize(phrase)) for phrase in spec.phrases]

    # 1) 완전 일치 — 가장 확실하다
    for phrase, norm in candidates:
        if norm and body == norm:
            return IntentMatch(spec.intent, 1.0, phrase, "exact", body, spec)

    # 2) 부분 일치 — "어 그래 전화 받아줘" 처럼 앞뒤가 붙는 경우.
    #    두 글자짜리 조각이 긴 문장 아무 데나 걸리면 오탐이므로 길이를 본다.
    for phrase, norm in candidates:
        if len(norm) >= 3 and norm in body:
            return IntentMatch(spec.intent, 0.9, phrase, "contains", body, spec)

    # 3) 키워드 묶음 — 어순이 달라도 필요한 낱말이 다 있으면 인정
    for keywords in spec.keyword_sets:
        normalized = [normalize(word) for word in keywords]
        if all(word and word in body for word in normalized):
            return IntentMatch(spec.intent, 0.85, " ".join(keywords), "keywords", body, spec)

    # 4) 자모 유사도 — 발음이 흐려 글자가 어긋난 경우의 마지막 그물
    threshold = _STRICT_RATIO if spec.intent in _STRICT_INTENTS else FUZZY_RATIO
    best_ratio, best_phrase = 0.0, ""
    for phrase, norm in candidates:
        if len(norm) < 3:
            continue  # 너무 짧은 조각은 아무 말에나 비슷해진다
        ratio = similarity(body, norm)
        if ratio > best_ratio:
            best_ratio, best_phrase = ratio, phrase
    if best_ratio >= threshold:
        return IntentMatch(spec.intent, round(best_ratio, 3), best_phrase, "fuzzy", body, spec)

    return None


def match_intent(
    text: str,
    *,
    context: IntentContext = IntentContext.IDLE,
) -> IntentMatch | None:
    """STT 결과 한 줄 → 인텐트. 상황에 맞지 않으면 None.

    상황 게이팅이 핵심이다. "받아줘"는 전화가 울릴 때만 전화를 받는다.
    평소 대화 중에 나온 같은 말은 그냥 모델로 흘려보낸다.
    """
    body = normalize(text)
    if not body:
        return None

    permitted = set(allowed_intents(context))
    best: IntentMatch | None = None
    for spec in INTENT_SPECS:
        if spec.intent not in permitted:
            continue
        found = _match_spec(spec, body)
        if found is None:
            continue
        if best is None or found.confidence > best.confidence:
            best = found
    return best


def intent_prompt(intent: VoiceIntent) -> str:
    spec = _BY_INTENT.get(intent)
    return spec.prompt if spec else ""


def example_phrases(intent: VoiceIntent) -> tuple[str, ...]:
    spec = _BY_INTENT.get(intent)
    return spec.phrases if spec else ()
