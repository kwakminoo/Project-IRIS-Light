from pathlib import Path

import pytest

from services.voice_runtime.tone_router import (
    TONE_BRIEFING,
    TONE_CAUTION,
    TONE_NARRATION,
    TONE_NEUTRAL,
    TONE_NUMERIC,
    TONE_QUESTION,
    TONES,
    classify_text_tone,
    is_expressive,
    parse_emotion_label,
    tone_for_recording,
)


@pytest.mark.parametrize(
    ("stem", "expected"),
    [
        ("1. 기쁨 · 축하 — 요청 성공 보고", "기쁨 · 축하"),
        ("3. 단호 · 확인 — 위험한 요청 재확인", "단호 · 확인"),
        ("10. 머뭇거림 B — 민감한 메시지 초안", "머뭇거림 B"),
        ("파일 검색이 끝났습니다.", "파일 검색이 끝났습니다."),
    ],
)
def test_parse_emotion_label(stem, expected):
    assert parse_emotion_label(stem) == expected


@pytest.mark.parametrize(
    "label", ["빈정거림 A", "짜증 B", "한탄 A", "화남 B", "머뭇거림 A"]
)
def test_expressive_labels_are_detected(label):
    assert is_expressive(label)


@pytest.mark.parametrize("label", ["차분 · 안내", "공감 · 위로", "정중 · 후속"])
def test_calm_labels_are_not_expressive(label):
    assert not is_expressive(label)


@pytest.mark.parametrize(
    ("relative", "expected"),
    [
        ("A. 긴문장/3. 단호 · 확인 — 위험한 요청 재확인.m4a", TONE_CAUTION),
        ("A. 긴문장/2. 차분 · 안내 — 아침 브리핑.m4a", TONE_NEUTRAL),
        ("A. 긴문장/7. 경쾌 · 요약 — 하루 마감 리포트.m4a", TONE_BRIEFING),
        ("B. 숫자·시간·날짜·금액·연락처·경로/지금은 오전 9시 12분입니다..m4a", TONE_NUMERIC),
        ("C. 의문·확인·선택 질문/화면 공유를 시작할까요.m4a", TONE_QUESTION),
        ("D. 나열·브리핑형/보안 점검 결과입니다.m4a", TONE_BRIEFING),
        ("E. 담담한 일상 비서 문장/파일 검색이 끝났습니다.m4a", TONE_NEUTRAL),
        ("G. 정중 거절· Clarification·대기·오류/연결이 끊겼습니다.m4a", TONE_CAUTION),
        ("H. 중길이 혼합 낭독/팀 공지 초안입니다.m4a", TONE_NARRATION),
    ],
)
def test_tone_for_recording(relative, expected):
    assert tone_for_recording(Path("녹음") / relative) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("회의실 예약을 완료했습니다.", TONE_NEUTRAL),
        ("이 작업은 파일을 삭제할 수 있습니다.", TONE_CAUTION),
        ("보안 정책상 그 요청은 진행할 수 없습니다.", TONE_CAUTION),
        ("지금 바로 보낼까요?", TONE_QUESTION),
        ("회신 톤을 공식적으로 할까요, 편하게 할까요", TONE_QUESTION),
        ("오늘 확인할 항목은 세 가지입니다.", TONE_BRIEFING),
        ("정리하면 배포와 로그 점검이 남았습니다.", TONE_BRIEFING),
        ("지금은 오전 아홉 시 십이 분이고, 미읽음 메일은 17통입니다.", TONE_NUMERIC),
        ("회의는 오후 2시 30분에 시작하고, 참석자는 8명입니다.", TONE_NUMERIC),
        ("백업 경로는 C:\\Users\\iris 입니다.", TONE_NUMERIC),
    ],
)
def test_classify_text_tone(text, expected):
    assert classify_text_tone(text) == expected


def test_caution_wins_over_question():
    # 위험 고지가 질문 형태로 오면 경고 톤이 우선이어야 한다.
    assert classify_text_tone("이 작업은 되돌릴 수 없습니다. 계속할까요?") == TONE_CAUTION


def test_long_text_falls_back_to_narration():
    body = "오전 업무 시작을 돕겠습니다. " * 8
    assert classify_text_tone(body) == TONE_NARRATION


def test_empty_text_is_neutral():
    assert classify_text_tone("") == TONE_NEUTRAL
    assert classify_text_tone("   ") == TONE_NEUTRAL


def test_every_classified_tone_is_a_known_tone():
    samples = [
        "안녕하세요",
        "삭제할까요?",
        "세 가지입니다",
        "오후 세 시 십 분입니다",
        "긴 문장입니다. " * 20,
    ]
    for text in samples:
        assert classify_text_tone(text) in TONES
