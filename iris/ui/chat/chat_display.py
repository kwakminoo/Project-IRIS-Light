"""채팅창 표시용 본문 정규화 (화자 접두사 제거·마크다운 렌더링)."""

from __future__ import annotations

import html
import re

from iris.core.markdown_text import (
    markdown_to_chat_html,
    markdown_to_plain,
    markdown_to_plain_partial,
)

_IRIS_PREFIX = re.compile(r"^\s*Iris\s*:\s*", re.IGNORECASE)


def strip_speaker_prefix(who: str, text: str) -> str:
    """채팅 UI가 이미 화자 이름을 붙이므로 본문의 'Iris:' 접두사는 제거한다."""
    body = (text or "").strip()
    if who.strip().lower() == "iris":
        body = _IRIS_PREFIX.sub("", body, count=1).strip()
    return body


def normalize_chat_body(who: str, text: str) -> str:
    """채팅 패널에 넣기 전 본문 정리 (마크다운 원문 유지, 이모지 제거)."""
    from iris.core.activity_privacy import prepare_chat_text

    return strip_speaker_prefix(who, prepare_chat_text(text))


def chat_body_to_html(text: str) -> str:
    """QTextEdit 본문 삽입용 HTML — render_user_message thin wrapper."""
    from iris.ui.chat.chat_renderer import render_user_message

    return render_user_message(text)


def visible_typing_text(
    source: str,
    source_index: int,
    *,
    render_markdown: bool = False,
) -> str:
    """타이핑 중 화면에 보일 평문 — 마크다운은 즉시 읽기 쉬운 형태로 변환."""
    partial = (source or "")[: max(0, source_index)]
    if not partial:
        return ""
    if render_markdown:
        return markdown_to_plain_partial(partial)
    return partial


def typing_body_to_html(text: str) -> str:
    """타이핑 중 본문 HTML — 공백·줄바꿈이 HTML 접힘 없이 그대로 보이게 한다."""
    escaped = html.escape(text or "")
    return f'<span style="color:#e8f0fe;white-space:pre-wrap;">{escaped}</span>'


# 타이핑 속도 기본값 (speech_sync 없을 때)
TYPING_INTERVAL_MS = 50
TYPING_CHARS_PER_TICK = 1
# TTS 동기화 시 한 틱에 따라잡을 최대 글자 수 (급격한 점프 방지)
TYPING_SPEECH_MAX_CHARS_PER_TICK = 4
# TTS보다 짧게 끝나지 않도록 최소 글자/초 (느릴수록 값을 낮춤)
TYPING_SPEECH_MIN_CHARS_PER_SEC = 12.0


def effective_typing_duration_ms(
    text_len: int,
    speech_duration_ms: float,
    *,
    min_chars_per_sec: float = TYPING_SPEECH_MIN_CHARS_PER_SEC,
) -> float:
    """TTS 길이와 최소 타이핑 시간 중 더 느린 값을 반환한다."""
    speech_ms = max(200.0, float(speech_duration_ms))
    if text_len <= 0:
        return speech_ms
    min_ms = text_len / max(min_chars_per_sec, 1.0) * 1000.0
    return max(speech_ms, min_ms)


def typing_target_index(text_len: int, elapsed_ms: float, duration_ms: float) -> int:
    """speech_sync 타이핑에서 현재까지 표시할 글자 수."""
    if text_len <= 0 or duration_ms <= 0:
        return 0
    ratio = min(1.0, max(0.0, elapsed_ms / duration_ms))
    return min(text_len, int(text_len * ratio))


def scale_typing_duration_ms(
    speech_duration_ms: float,
    visible_len: int,
    spoken_len: int,
) -> float:
    """TTS 구간 길이를 채팅에 보이는 글자 수 비율로 스케일."""
    spoken = max(int(spoken_len), 1)
    visible = max(int(visible_len), 0)
    return max(200.0, float(speech_duration_ms)) * (visible / spoken)


def extend_typing_timeline_ms(
    elapsed_ms: float,
    remaining_chars: int,
    segment_duration_ms: float,
    *,
    min_chars_per_sec: float = TYPING_SPEECH_MIN_CHARS_PER_SEC,
) -> float:
    """후속 TTS 세그먼트 — 경과 시간 + 남은 본문 타이핑 예산."""
    segment_ms = effective_typing_duration_ms(
        remaining_chars,
        segment_duration_ms,
        min_chars_per_sec=min_chars_per_sec,
    )
    return max(elapsed_ms, 0.0) + segment_ms


def streaming_segments_html(
    segments: list,
    typing_index: int,
    *,
    render_markdown: bool = False,
    tool_blocks: dict | None = None,
) -> str:
    """prose는 typing_index까지, code/tool은 즉시 HTML."""
    from iris.core.chat_block_parser import CodeSegment, ProseSegment, ToolSegment
    from iris.ui.chat.chat_blocks import (
        FencedCodeBlock,
        fenced_code_to_html,
        marked_tool_shell_to_html,
        wrap_document_html,
    )

    remaining = max(0, int(typing_index))
    parts: list[str] = []
    registry = tool_blocks if tool_blocks is not None else {}
    for seg in segments:
        if isinstance(seg, ProseSegment):
            if remaining <= 0:
                break
            take = seg.text[:remaining]
            remaining -= len(take)
            if not take:
                continue
            visible = visible_typing_text(take, len(take), render_markdown=render_markdown)
            parts.append(typing_body_to_html(visible))
            if len(take) < len(seg.text):
                break
        elif isinstance(seg, CodeSegment):
            parts.append(
                wrap_document_html(
                    fenced_code_to_html(
                        FencedCodeBlock(seg.code, language=seg.language)
                    )
                )
            )
        elif isinstance(seg, ToolSegment) and seg.complete:
            block = seg.block
            bid = (block.block_id or "").strip()
            if bid:
                registry[bid] = block
            parts.append(wrap_document_html(marked_tool_shell_to_html(block)))
    return "".join(parts)
