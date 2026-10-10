"""세션이 끝날 때 에피소드와 얇은 특성 노트를 남긴다."""

from __future__ import annotations

import re
from typing import Callable

from iris.knowledge.history_store import write_episode
from iris.knowledge.iris_wiki import IrisWiki
from iris.knowledge.wiki_classify import parse_model_json
from iris.knowledge.wiki_note_index import index_rel
from iris.knowledge.wiki_places import TRAITS_REL, is_sensitive
from iris.storage.database import Database

SESSION_SYSTEM = (
    "대화 묶음을 Iris Wiki용으로 정리한다. JSON만 출력한다. "
    "성격 점수를 매기지 않는다. 없는 항목은 빈 문자열이다. "
    '{"title":"","summary":"","interests":"","level":"","improved":""}'
)

_MARKER = "<!-- iris-traits -->"
_MAX_SECTIONS = 12
_TRAITS_CAP = 1500
_TRAITS_HEADER = (
    "# 사용자 특성 노트 (profile/traits.md)\n\n"
    "아래는 위키에 적어 둔 관심사·수준·성장이다. 대화 원문이나 학습 노트와 다른 출처다. "
    "사용자가 이 파일에서 고친 내용이 우선이다. 성격 점수를 말하지 마라.\n\n"
)
Summarizer = Callable[[str], str]


def transcript_of(messages: list[dict]) -> str:
    lines = []
    for message in messages or []:
        content = str(message.get("content") or "").strip()
        if content:
            lines.append(f"{message.get('role') or 'user'}: {content}")
    text = "\n\n".join(lines)
    return text[-8000:] if len(text) > 8000 else text


def usable_turns(messages: list[dict]) -> int:
    return sum(1 for message in messages or [] if str(message.get("content") or "").strip())


def merge_traits(existing: str, section: str) -> str:
    """마커 위는 사용자가 고친 글로 유지하고, 자동 섹션은 최근 12개만 둔다."""
    text = existing or ""
    if _MARKER in text:
        header, _, tail = text.partition(_MARKER)
    else:
        header = text if text.strip() else (
            "# 사용자 특성\n\n"
            "> 관심사·지금 수준·이번에 나아진 점만 적는다. 성격 점수는 적지 않는다.\n"
        )
        tail = ""
    parts = [part.strip() for part in re.split(r"(?m)(?=^## )", tail) if part.strip()]
    if section.strip():
        parts.append(section.strip())
    parts = parts[-_MAX_SECTIONS:]
    body = "\n\n".join(parts)
    return header.rstrip() + "\n\n" + _MARKER + "\n\n" + (body + "\n" if body else "")


def render_trait_section(
    *,
    stamp: str,
    conversation_id: int,
    interests: str,
    level: str,
    improved: str,
    episode_title: str,
) -> str:
    lines = [f"## {stamp} · conv {conversation_id}", ""]
    if interests:
        lines.append(f"- 관심사: {interests}")
    if level:
        lines.append(f"- 지금 수준: {level}")
    if improved:
        lines.append(f"- 이번에 나아진 점: {improved}")
    if episode_title:
        lines.append(f"- 근거: [[{episode_title}]]")
    return "" if len(lines) == 2 else "\n".join(lines)


def traits_prompt_block(wiki: IrisWiki) -> str:
    path = wiki.user_root / TRAITS_REL
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    if not text or is_sensitive(text):
        return ""
    if len(text) > _TRAITS_CAP:
        text = text[:_TRAITS_CAP]
    return _TRAITS_HEADER + text + "\n"


def close_session(
    db: Database,
    wiki: IrisWiki,
    *,
    conversation_id: int,
    messages: list[dict],
    summarize: Summarizer,
    model: str = "",
    episode_dir: str = "",
) -> bool:
    """요약이 비거나 말이 모자라면 파일을 만들지 않는다."""
    if usable_turns(messages) < 2 or not transcript_of(messages):
        return False
    try:
        raw = summarize("다음 대화를 정리해 JSON만 돌려라.\n\n" + transcript_of(messages))
    except Exception:
        return False
    data = parse_model_json(raw or "")
    summary = str(data.get("summary") or "").strip()
    if not summary:
        return False
    title = str(data.get("title") or "").strip() or f"대화 {conversation_id}"
    entry = write_episode(
        db, wiki, title=title, summary=summary,
        conversation_id=int(conversation_id or 0), model=model,
        covers=_covers(db, conversation_id),
        folder=episode_dir,
    )
    if entry is None:
        return False
    section = render_trait_section(
        stamp=entry.created_at,
        conversation_id=int(conversation_id or 0),
        interests=str(data.get("interests") or "").strip(),
        level=str(data.get("level") or "").strip(),
        improved=str(data.get("improved") or "").strip(),
        episode_title=entry.title or title,
    )
    if not section:
        return True
    path = wiki.user_root / TRAITS_REL
    current = ""
    if path.is_file():
        try:
            current = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            current = ""
    wiki.write_user_note(TRAITS_REL, merge_traits(current, section))
    try:
        index_rel(db, wiki, TRAITS_REL, place_id="profile")
    except OSError:
        pass
    return True


def _covers(db: Database, conversation_id: int):
    if not conversation_id:
        return None
    try:
        row = db._execute(
            "SELECT MIN(id) AS a, MAX(id) AS b FROM wiki_history WHERE conversation_id = ?",
            (int(conversation_id),),
        ).fetchone()
    except Exception:
        return None
    if row is None or row["a"] is None:
        return None
    return int(row["a"]), int(row["b"])
