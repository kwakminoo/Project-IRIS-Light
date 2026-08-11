"""화면 상태 판정 — 모델 응답 파싱과 실패 흡수."""

from __future__ import annotations

from unittest import TestCase

from iris.monitoring.models import StatusCategory
from iris.monitoring.state_detector import detect_window_state, parse_detection


class ParseDetectionTests(TestCase):
    def test_plain_json(self) -> None:
        r = parse_detection(
            '{"category":"TASK_STALLED","confidence":0.82,'
            '"reason":"진행률이 12%에서 멈춰 있음","recommended_action":"로그 확인"}'
        )
        self.assertEqual(r.category, StatusCategory.TASK_STALLED)
        self.assertAlmostEqual(r.confidence, 0.82)
        self.assertEqual(r.reason, "진행률이 12%에서 멈춰 있음")
        self.assertEqual(r.recommended_action, "로그 확인")

    def test_code_fenced_json(self) -> None:
        r = parse_detection(
            '```json\n{"category":"ERROR_DETECTED","confidence":0.9,'
            '"reason":"빨간 에러","recommended_action":""}\n```'
        )
        self.assertEqual(r.category, StatusCategory.ERROR_DETECTED)

    def test_json_with_surrounding_prose(self) -> None:
        """모델이 잡담을 붙여도 JSON만 건져야 한다."""
        r = parse_detection(
            '분석 결과입니다: {"category":"NORMAL","confidence":0.7,'
            '"reason":"정상","recommended_action":""} 이상입니다.'
        )
        self.assertEqual(r.category, StatusCategory.NORMAL)

    def test_unknown_category_falls_back(self) -> None:
        r = parse_detection('{"category":"EXPLODED","confidence":0.99,"reason":"x"}')
        self.assertEqual(r.category, StatusCategory.UNKNOWN)
        # 카테고리를 못 알아들었으면 confidence도 믿을 수 없다
        self.assertEqual(r.confidence, 0.0)

    def test_confidence_is_clamped(self) -> None:
        r = parse_detection('{"category":"NORMAL","confidence":7.5,"reason":"x"}')
        self.assertEqual(r.confidence, 1.0)
        r2 = parse_detection('{"category":"NORMAL","confidence":-3,"reason":"x"}')
        self.assertEqual(r2.confidence, 0.0)

    def test_non_numeric_confidence(self) -> None:
        r = parse_detection('{"category":"NORMAL","confidence":"높음","reason":"x"}')
        self.assertEqual(r.confidence, 0.0)

    def test_garbage_response(self) -> None:
        for text in ("", "   ", "모르겠습니다", "{{{"):
            r = parse_detection(text)
            self.assertEqual(r.category, StatusCategory.UNKNOWN)
            self.assertEqual(r.confidence, 0.0)


class _FakeClient:
    def __init__(self, reply: str = "", raises: Exception | None = None) -> None:
        self.reply = reply
        self.raises = raises
        self.calls: list[dict] = []

    def chat_once_with_images(self, model, prompt, images, *, system="", timeout_sec=90.0):
        self.calls.append(
            {"model": model, "prompt": prompt, "images": images, "system": system}
        )
        if self.raises:
            raise self.raises
        return self.reply


class DetectWindowStateTests(TestCase):
    def test_sends_image_and_parses(self) -> None:
        client = _FakeClient('{"category":"APPROVAL_WAITING","confidence":0.75,"reason":"확인 팝업"}')
        r = detect_window_state(client, "gemma4:e4b", "빌드 창", b"\x89PNG-fake")
        self.assertEqual(r.category, StatusCategory.APPROVAL_WAITING)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0]["images"], [b"\x89PNG-fake"])
        self.assertIn("빌드 창", client.calls[0]["prompt"])

    def test_model_error_is_absorbed(self) -> None:
        """모델이 죽어도 감시 루프가 예외로 멈추면 안 된다."""
        client = _FakeClient(raises=RuntimeError("Ollama 연결 실패"))
        r = detect_window_state(client, "gemma4:e4b", "창", b"png")
        self.assertEqual(r.category, StatusCategory.UNKNOWN)
        self.assertIn("분석 실패", r.reason)

    def test_missing_model_or_image_skips_call(self) -> None:
        client = _FakeClient('{"category":"NORMAL","confidence":1}')
        self.assertEqual(
            detect_window_state(client, "", "창", b"png").category, StatusCategory.UNKNOWN
        )
        self.assertEqual(
            detect_window_state(client, "m", "창", b"").category, StatusCategory.UNKNOWN
        )
        self.assertEqual(client.calls, [])
