"""위키 저장용 본문 요약. 채팅에서 고른 모델(Ollama·API·Hermes)로 한 번 묻는다."""

from __future__ import annotations

_SYSTEM = (
    "You summarize source text for an Iris Wiki note. "
    "Output Korean markdown with exactly these two headings and nothing before them:\n"
    "## 전체 요약\n"
    "A short overview of the whole passage.\n"
    "## 핵심 개념\n"
    "Bullet list of the key concepts. No preamble."
)

# ponytail: 한 호출 분량. 저장 상한이 아니다. 더 긴 글은 순서대로 나눈 뒤 다시 합친다.
_CHUNK = 24_000


def _chunks(text: str, size: int) -> list[str]:
    body = (text or "").strip()
    if len(body) <= size:
        return [body] if body else []
    out: list[str] = []
    start = 0
    while start < len(body):
        end = min(len(body), start + size)
        if end < len(body):
            cut = body.rfind("\n", start, end)
            if cut > start + size // 2:
                end = cut
        piece = body[start:end].strip()
        if piece:
            out.append(piece)
        start = end
    return out


def _ask(text: str, *, model: str, ollama_base_url: str, settings, db, system: str) -> str:
    from iris.runtime.backend_route import ask_selected_model, settings_for_model

    return ask_selected_model(
        settings_for_model(settings, ollama_base_url),
        db,
        model,
        text,
        system=system,
        timeout_sec=120.0,
    )


def _summarize_once(
    text: str,
    *,
    model: str,
    ollama_base_url: str,
    preface: str,
    settings=None,
    db=None,
) -> str:
    prompt = f"{preface}\n\n---\n{text}\n---"
    out = _ask(
        prompt,
        model=model,
        ollama_base_url=ollama_base_url,
        settings=settings,
        db=db,
        system=_SYSTEM,
    )
    summary = (out or "").strip()
    if not summary:
        raise RuntimeError("empty summary from model")
    return summary


def summarize_for_wiki(
    text: str,
    *,
    model: str,
    ollama_base_url: str,
    max_input_chars: int = _CHUNK,
    settings=None,
    db=None,
) -> str:
    """전체 글을 빠뜨리지 않고 요약한다. max_input_chars 는 호출 한 번의 길이일 뿐이다."""
    body = (text or "").strip()
    if not body:
        raise ValueError("empty text")
    size = max(int(max_input_chars or _CHUNK), 1_000)
    pieces = _chunks(body, size)
    preface = "다음 자료를 Iris Wiki 노트용으로 요약해 주세요."
    if len(pieces) <= 1:
        return _summarize_once(
            pieces[0],
            model=model,
            ollama_base_url=ollama_base_url,
            preface=preface,
            settings=settings,
            db=db,
        )
    parts: list[str] = []
    for index, piece in enumerate(pieces, 1):
        parts.append(
            _summarize_once(
                piece,
                model=model,
                ollama_base_url=ollama_base_url,
                preface=f"자료의 {index}/{len(pieces)} 부분만 요약해 주세요.",
                settings=settings,
                db=db,
            )
        )
    merged = "\n\n".join(f"### 부분 {index}\n{part}" for index, part in enumerate(parts, 1))
    # 부분 요약이 다시 한 호출보다 길면 같은 방식으로 접는다. 8단이면 멈춘다.
    for _ in range(8):
        if len(merged) <= size:
            break
        folded = _chunks(merged, size)
        if len(folded) <= 1:
            break
        merged = "\n\n".join(
            _summarize_once(
                piece,
                model=model,
                ollama_base_url=ollama_base_url,
                preface="아래 부분 요약을 더 짧게 합쳐 주세요.",
                settings=settings,
                db=db,
            )
            for piece in folded
        )
    return _summarize_once(
        merged,
        model=model,
        ollama_base_url=ollama_base_url,
        preface="아래는 부분을 나눈 요약이다. 하나의 전체 요약과 핵심 개념으로 합쳐 주세요.",
        settings=settings,
        db=db,
    )


_TRANSLATE_SYSTEM = (
    "You translate one paragraph into Korean for an Iris Wiki note. "
    "Output only the Korean paragraph. No preamble, no quotes, no original text."
)


def translate_for_wiki(
    text: str,
    *,
    model: str,
    ollama_base_url: str,
    settings=None,
    db=None,
) -> str:
    """문단 하나. 완료 문장이나 도구 호출을 하지 않는다."""
    body = (text or "").strip()
    if not body:
        return ""
    if len(body) > 4_000:
        body = body[:4_000]
    prompt = f"다음 문단을 한국어로 번역해 주세요.\n\n{body}"
    out = _ask(
        prompt,
        model=model,
        ollama_base_url=ollama_base_url,
        settings=settings,
        db=db,
        system=_TRANSLATE_SYSTEM,
    )
    return (out or "").strip()
