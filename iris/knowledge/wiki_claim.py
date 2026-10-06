"""위키 작업 목표를 가린다. 답 문장은 모델이 쓴 그대로 둔다."""

from __future__ import annotations


def relocate_goal(goal: str) -> bool:
    """이미 있는 노트를 폴더로 보내라는 목표. 새 글 저장과는 구분한다."""
    text = goal or ""
    folded = text.lower()
    place = any(word in text for word in ("학습자료", "폴더", "위키", "노트")) or "inbox" in folded
    if any(word in text for word in ("옮", "이동", "분류")) and place:
        return True
    return "학습자료" in text and "폴더" in text and "저장" in text


def wiki_work_goal(goal: str) -> bool:
    if relocate_goal(goal):
        return True
    text = goal or ""
    folded = text.lower()
    if any(word in text for word in ("원문", "문단", "번역", "덮어")):
        return True
    wiki = any(word in text for word in ("위키", "노트", "문서")) or "wiki" in folded or "가져오" in text
    work = any(word in text for word in ("저장", "가져오", "정리", "번역", "요약", "열", "삭제", "만들", "바꿔", "변경"))
    return wiki and work


def settle_wiki_claim(
    text: str,
    *,
    goal: str = "",
    wrote: bool = False,
    opened: bool = False,
    changed: bool | None = None,
    moved: bool = False,
) -> str:
    """모델이 쓴 답을 그대로 둔다."""
    del goal, wrote, opened, changed, moved
    return text or ""


def _check() -> None:
    goal = "원문은 남기고 위에 정리, 문단 아래 한국어"
    said = "정리했습니다."
    assert settle_wiki_claim(said, goal=goal, wrote=False) == said
    assert settle_wiki_claim(said, goal=goal, wrote=True, changed=False) == said
    kept = "정리했습니다. user/inbox/a.md"
    assert settle_wiki_claim(kept, goal=goal, wrote=True, changed=True) == kept
    opened = "열어 드리겠습니다."
    assert settle_wiki_claim(opened, goal="정리된 위키를 열어", opened=False) == opened
    assert settle_wiki_claim("작성했습니다.", goal="스크립트 작성해줘") == "작성했습니다."
    assert not wiki_work_goal("오늘 날씨 알려줘")
    arrange = "학습자료 폴더를 만들어 강화학습으로 분류해서 저장"
    assert relocate_goal(arrange)
    moved = "분류해 저장했습니다."
    assert settle_wiki_claim(moved, goal=arrange, wrote=True, moved=False) == moved
    assert "노트는 그대로다" not in settle_wiki_claim(moved, goal=arrange, wrote=False, moved=False)
    assert not relocate_goal("위키에 저장")
    print("wiki_claim ok")


if __name__ == "__main__":
    _check()
