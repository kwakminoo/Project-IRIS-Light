"""채팅 목록 클릭 — 탐색기처럼 Ctrl 은 토글, Shift 는 범위."""

from __future__ import annotations


def apply_list_click(
    order: list[tuple[str, int]],
    selected: list[tuple[str, int]],
    anchor: tuple[str, int] | None,
    key: tuple[str, int],
    *,
    ctrl: bool,
    shift: bool,
) -> tuple[list[tuple[str, int]], tuple[str, int] | None]:
    """보이는 순서 `order` 안에서 다음 선택과 기준점을 돌려준다."""
    visible = list(order)
    if key not in visible:
        kept = [item for item in selected if item in visible]
        return kept, anchor if anchor in visible else (kept[-1] if kept else None)
    current = [item for item in selected if item in visible]
    if shift:
        start = anchor if anchor in visible else visible[0]
        lo = visible.index(start)
        hi = visible.index(key)
        if lo > hi:
            lo, hi = hi, lo
        span = visible[lo : hi + 1]
        if ctrl:
            merged: list[tuple[str, int]] = []
            for item in [*current, *span]:
                if item not in merged:
                    merged.append(item)
            return merged, start
        return span, start
    if ctrl:
        if key in current:
            current = [item for item in current if item != key]
        else:
            current = [*current, key]
        return current, key
    return [key], key
