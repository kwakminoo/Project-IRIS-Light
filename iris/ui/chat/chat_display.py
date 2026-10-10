"""채팅창 표시용 본문 정규화 (화자 접두사 제거·마크다운 렌더링)."""

from __future__ import annotations

import html
import re

from iris.core.markdown_text import (
    markdown_to_chat_html,
    markdown_to_plain,
    markdown_to_plain_partial,
)
from iris.ui.chat.typography import TOKENS

_IRIS_PREFIX = re.compile(
    r"^\s*(?:\*\*Iris\*\*\s*:|\*\*Iris\s*:\*\*|Iris\s*:)\s*",
    re.IGNORECASE,
)


def strip_speaker_prefix(who: str, text: str) -> str:
    """채팅 UI가 이미 화자 이름을 붙이므로 본문의 'Iris:' 접두사는 제거한다."""
    body = (text or "").strip()
    if who.strip().lower() == "iris":
        while _IRIS_PREFIX.match(body):
            body = _IRIS_PREFIX.sub("", body, count=1).strip()
    return body


def normalize_chat_body(who: str, text: str) -> str:
    """채팅 패널에 넣기 전 본문 정리 (마크다운 원문 유지, 이모지 제거)."""
    from iris.core.activity_privacy import prepare_chat_text

    return strip_speaker_prefix(who, prepare_chat_text(text))


# Keep explanatory Markdown and code in the chat; internal tool markers and
# private paths are filtered independently without modifying the raw buffer.
_TOOL_MARK = "IRIS_TOOL_"
_URL_RE = re.compile(r"https?://[^\s<>)\]]+", re.IGNORECASE)
# ponytail: 청크 끝의 슬래시 토큰은 경로로 보고 보류한다. and/or 도 다음 청크·종료 전까지 숨는다.
_HOLD_PATH = re.compile(
    r"(?:(?<![A-Za-z0-9_])[A-Za-z]:[\\/]?"
    r"|\\\\"
    r"|/(?:Users|home|var|tmp|opt|usr)(?:/[A-Za-z0-9_.\\/-]*)?"
    r"|(?:[A-Za-z0-9_.-]+[\\/])+[A-Za-z0-9_.-]*)\Z"
)


def assistant_visible_text(raw: str, *, streaming: bool) -> str:
    """Iris 답변 원문 → 화면용 텍스트.

    설명과 코드 펜스는 유지하고, 내부 도구 표식과 불필요한 경로를 정리한다.
    미완성 코드도 닫힌 표시용 펜스로 감싸 원문 기호 노출을 막는다.
    """
    from iris.core.chat_block_parser import CodeSegment, ProseSegment, parse_chat_segments

    parts: list[str] = []
    for seg in parse_chat_segments(strip_speaker_prefix("Iris", raw or ""), final=not streaming):
        if isinstance(seg, ProseSegment):
            prose = _drop_dangling_tool(seg.text)
            if streaming:
                prose = _streaming_head(prose)
            parts.append(_replace_unnecessary_paths(prose))
        elif isinstance(seg, CodeSegment):
            parts.append(f"\n\n```{seg.language}\n{seg.code}\n```\n\n")
    return "".join(parts).strip()


def _drop_dangling_tool(text: str) -> str:
    """파서가 블록으로 못 자른 IRIS_TOOL_ 조각. 완성 문장은 유지."""
    out: list[str] = []
    idx = 0
    while True:
        found = text.find(_TOOL_MARK, idx)
        if found < 0:
            out.append(text[idx:])
            break
        out.append(text[idx:found])
        line_end = text.find("\n", found)
        if line_end < 0:
            break
        idx = line_end + 1
    return "".join(out)


def _streaming_head(text: str) -> str:
    """끝나지 않은 펜스·경로·도구 접두사는 다음 청크까지 보류."""
    while True:
        nxt = _cut_streaming_suffix(text)
        if nxt == text:
            return text
        text = nxt


def _cut_streaming_suffix(text: str) -> str:
    for size in range(len(_TOOL_MARK), 3, -1):
        if text.endswith(_TOOL_MARK[:size]):
            return text[:-size]
    fence = re.search(r"(?:^|\n)(`{1,2})\Z", text)
    if fence:
        return text[: fence.start(1)]
    held = _HOLD_PATH.search(text)
    if held is not None and not _token_is_url(text, held.start()):
        return text[: held.start()]
    return text


def _token_is_url(text: str, start: int) -> bool:
    cut = max(text.rfind(ch, 0, start) for ch in " \n\t(")
    token = text[cut + 1 :].lower()
    return token.startswith("http://") or token.startswith("https://")


def _replace_unnecessary_paths(text: str) -> str:
    """절대·다단 경로는 파일 이름만 남긴다. URL 은 그대로."""
    from iris.ui.chat.chat_renderer import _FILE_EXT

    masked, urls = _mask_urls(text)
    line = r"(?::\d+(?::\d+)?)?"
    path_re = re.compile(
        rf"(?<![A-Za-z0-9_./:\\-])(?<!://)"
        rf"("
        rf"[A-Za-z]:[\\/][^\\/:*?\"<>|`\r\n]+(?:[\\/][^\\/:*?\"<>|`\r\n]+)*"
        rf"|\\\\[A-Za-z0-9_.\-\\/:]+"
        rf"|/(?:Users|home|var|tmp|opt|usr)/[A-Za-z0-9_.\-\\/:]+"
        rf"|(?:[A-Za-z0-9_.-]+[\\/])+[A-Za-z0-9_.-]+\.{_FILE_EXT}{line}"
        rf")"
    )

    def repl(match: re.Match[str]) -> str:
        token = match.group(0)
        core = token.rstrip(".,;!?)]}\"'")
        tail = token[len(core) :]
        if not _has_file_ext(core):
            return f"작업 폴더{tail}"
        name = _basename(core)
        return f"{name}{tail}" if name else tail

    return _unmask_urls(path_re.sub(repl, masked), urls)


def _has_file_ext(path: str) -> bool:
    from iris.ui.chat.chat_renderer import _FILE_EXT

    name = _basename(path)
    return bool(re.search(rf"\.{_FILE_EXT}\Z", name, re.IGNORECASE))


def _basename(path: str) -> str:
    name = path.replace("\\", "/").rstrip("/").split("/")[-1]
    if name in ("", ".", ".."):
        return ""
    head, sep, tail = name.rpartition(":")
    if sep and tail.isdigit() and head:
        name = head
    return name


def _mask_urls(text: str) -> tuple[str, list[str]]:
    found: list[str] = []

    def repl(match: re.Match[str]) -> str:
        found.append(match.group(0))
        return f"\ue000{len(found) - 1}\ue001"

    return _URL_RE.sub(repl, text), found


def _unmask_urls(text: str, urls: list[str]) -> str:
    for index, url in enumerate(urls):
        text = text.replace(f"\ue000{index}\ue001", url)
    return text


def _tidy(text: str) -> str:
    text = re.sub(r"`[ \t]*`", "", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


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
    return (
        f'<span style="color:{TOKENS.chat_body};line-height:{TOKENS.chat_line_height};'
        f'font-size:{TOKENS.chat_font_size};white-space:pre-wrap;">{escaped}</span>'
    )


# 타이핑 속도 기본값 (speech_sync 없을 때): 초당 20글자 = 50ms에 1글자
TYPING_INTERVAL_MS = 50
TYPING_CHARS_PER_TICK = 1
# TTS 동기화 시 한 틱에 따라잡을 최대 글자 수 (급격한 점프 방지)
TYPING_SPEECH_MAX_CHARS_PER_TICK = 4
# TTS보다 짧게 끝나지 않도록 최소 글자/초 (느릴수록 값을 낮춤)
TYPING_SPEECH_MIN_CHARS_PER_SEC = 12.0


def plain_typing_step(chars_per_sec: int | None = None) -> tuple[int, int]:
    """일반 타이핑 (interval_ms, 틱당 글자 수). 설정이 없으면 저장된 속도를 쓴다."""
    from iris.ui.chat.typography import (
        TYPING_CHARS_PER_SEC_MAX,
        TYPING_CHARS_PER_SEC_MIN,
        manager,
    )

    if chars_per_sec is None:
        chars_per_sec = manager.get().typing_chars_per_sec
    cps = max(TYPING_CHARS_PER_SEC_MIN, min(TYPING_CHARS_PER_SEC_MAX, int(chars_per_sec)))
    interval = round(1000 / cps)
    if interval >= 16:
        return interval, 1
    chars = max(1, (cps * 16 + 999) // 1000)
    return max(16, round(1000 * chars / cps)), chars


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
            if render_markdown:
                from iris.ui.chat.chat_renderer import render_iris_message
                parts.append(render_iris_message(take))
            else:
                parts.append(typing_body_to_html(take))
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
