"""위키 선택 구간 → 짧은 용어 설명 (채팅 턴을 열지 않음)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

# 단어·짧은 구. 문단 전체 드래그는 FAB를 숨긴다.
MAX_SELECTION_CHARS = 80
MIN_SELECTION_CHARS = 1

Explainer = Callable[[str, str, str], str]


@dataclass(frozen=True)
class SelectionExplainRequest:
    selection: str
    note_rel: str
    surrounding: str = ""


def selection_eligible_for_fab(text: str, *, max_chars: int = MAX_SELECTION_CHARS) -> bool:
    raw = (text or "").strip()
    if len(raw) < MIN_SELECTION_CHARS:
        return False
    if len(raw) > max_chars:
        return False
    return True


def default_explain_term(selection: str, note_rel: str = "", surrounding: str = "") -> str:
    """네트워크 없이 동작하는 짧은 설명. 주입 explainer가 없을 때 사용."""
    term = (selection or "").strip()
    if not term:
        return "선택한 텍스트가 없습니다."
    ctx = " ".join((surrounding or "").split())
    if ctx and term in ctx:
        # 문맥 한 조각만 보여 주고, 뜻은 짧게 안내.
        i = ctx.find(term)
        start = max(0, i - 24)
        end = min(len(ctx), i + len(term) + 24)
        snippet = ctx[start:end].strip()
        if start > 0:
            snippet = "…" + snippet
        if end < len(ctx):
            snippet = snippet + "…"
        where = f" ({note_rel})" if (note_rel or "").strip() else ""
        return (
            f"「{term}」{where}\n"
            f"이 페이지 문맥: {snippet}\n"
            f"전문 용어·약어일 수 있습니다. 위 문장 흐름 안에서 이해해 보세요."
        )
    where = f" (노트: {note_rel})" if (note_rel or "").strip() else ""
    return f"「{term}」{where}\n선택하신 표현의 짧은 뜻 설명을 준비하지 못했습니다. 문맥을 함께 선택해 보세요."


def explain_term(
    selection: str,
    note_rel: str = "",
    surrounding: str = "",
    *,
    explainer: Explainer | None = None,
) -> str:
    term = (selection or "").strip()
    if not term:
        return "선택한 텍스트가 없습니다."
    if len(term) > MAX_SELECTION_CHARS * 2:
        return "선택이 너무 깁니다. 단어나 짧은 구만 선택해 주세요."
    fn = explainer or default_explain_term
    try:
        text = fn(term, note_rel or "", surrounding or "")
    except Exception as exc:  # noqa: BLE001 — 팝오버에 한 줄만
        return f"설명을 가져오지 못했습니다: {exc}"
    out = (text or "").strip()
    if not out:
        return "설명이 비어 있습니다."
    # 장문 에세이 방지
    lines = [ln.rstrip() for ln in out.splitlines() if ln.strip()]
    if len(lines) > 6:
        lines = lines[:6]
    joined = "\n".join(lines)
    if len(joined) > 600:
        joined = joined[:597].rstrip() + "…"
    return joined
