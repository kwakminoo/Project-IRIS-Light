"""고정된 창의 화면을 멀티모달 모델로 분석해 작업 상태를 판정.

기획 의도: 사용자가 붙잡고 있지 않아도 "빌드가 멈췄다", "생성이 실패했다",
"승인 대기 중이다" 같은 상태를 Iris가 대신 알아채고 보고한다.

원본 스크린샷은 디스크에 저장하지 않고 메모리에서 모델로만 보낸다
(monitoring/models.py의 Safety Policy와 동일)."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Optional

from iris.monitoring.models import DetectionResult, StatusCategory

if TYPE_CHECKING:
    from iris.infrastructure.ollama_client import OllamaClient

_VALID = {c.value for c in StatusCategory}

_SYSTEM = (
    "You are a screen-state analyst. You are shown a screenshot of a single "
    "application window and must decide whether the work in that window is "
    "progressing normally or needs the user's attention. "
    "Answer with JSON only — no prose, no code fences."
)

_PROMPT = """이 창의 화면을 보고 현재 작업 상태를 판정하세요.

창 제목: {title}

가능한 category (반드시 이 중 하나):
- NORMAL: 정상 진행 중이거나 특별히 사용자 개입이 필요 없음
- APPROVAL_WAITING: 확인/승인/계속 여부를 사용자에게 묻는 중
- ERROR_DETECTED: 에러 메시지·예외·빨간 실패 표시가 보임
- GENERATION_FAILED: 생성/빌드/실행이 실패로 끝남
- TASK_STALLED: 진행 표시가 멈춰 있거나 오래 대기 중으로 보임
- RESPONSE_READY: 요청한 결과가 나와서 확인하면 되는 상태
- BUILD_NOT_STARTED: 시작 대기 상태로 아직 아무것도 실행되지 않음
- USER_ACTION_REQUIRED: 입력·선택 등 사용자 조작이 있어야 진행됨
- UNKNOWN: 화면만으로 판단이 어려움

JSON 형식 (이것만 출력):
{{"category": "...", "confidence": 0.0~1.0, "reason": "한국어 한 문장", "recommended_action": "한국어 한 문장"}}

reason에는 화면에서 실제로 보이는 근거를 쓰세요. 근거가 없으면 UNKNOWN에
confidence를 낮게 주세요. 추측으로 문제를 지어내지 마세요."""


def _extract_json(text: str) -> Optional[dict]:
    """모델이 코드펜스나 잡담을 섞어도 첫 JSON 객체를 건져낸다."""
    raw = (text or "").strip()
    if not raw:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fenced:
        raw = fenced.group(1)
    else:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end <= start:
            return None
        raw = raw[start : end + 1]
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def parse_detection(text: str) -> DetectionResult:
    """모델 응답 → DetectionResult. 파싱 실패는 UNKNOWN(confidence 0)."""
    obj = _extract_json(text)
    if obj is None:
        return DetectionResult(
            category=StatusCategory.UNKNOWN,
            confidence=0.0,
            reason="모델 응답을 해석하지 못했습니다.",
            recommended_action="",
        )

    raw_cat = str(obj.get("category") or "").strip().upper()
    category = StatusCategory(raw_cat) if raw_cat in _VALID else StatusCategory.UNKNOWN

    try:
        confidence = float(obj.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    # 카테고리를 못 알아들었으면 confidence도 신뢰할 수 없다
    if category is StatusCategory.UNKNOWN and raw_cat not in _VALID:
        confidence = 0.0

    return DetectionResult(
        category=category,
        confidence=confidence,
        reason=str(obj.get("reason") or "").strip()[:400],
        recommended_action=str(obj.get("recommended_action") or "").strip()[:200],
    )


def detect_window_state(
    client: "OllamaClient",
    model: str,
    title: str,
    png_bytes: bytes,
    *,
    timeout_sec: float = 90.0,
) -> DetectionResult:
    """창 스크린샷 1장을 모델에 보내 상태를 판정. 실패해도 예외를 던지지 않는다."""
    if not model or not png_bytes:
        return DetectionResult(
            category=StatusCategory.UNKNOWN,
            confidence=0.0,
            reason="분석할 모델 또는 화면이 없습니다.",
            recommended_action="",
        )
    try:
        text = client.chat_once_with_images(
            model,
            _PROMPT.format(title=title or "(제목 없음)"),
            [png_bytes],
            system=_SYSTEM,
            timeout_sec=timeout_sec,
        )
    except Exception as e:  # 네트워크·모델 오류는 UNKNOWN으로 흡수
        return DetectionResult(
            category=StatusCategory.UNKNOWN,
            confidence=0.0,
            reason=f"분석 실패: {e}"[:400],
            recommended_action="",
        )
    return parse_detection(text)
