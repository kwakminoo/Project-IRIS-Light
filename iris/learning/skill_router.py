"""채팅 문장 → 배운 스킬 고르기·넣을 값 뽑기. 모델 없이 즉시 (Hermes 가 꺼져 있어도).

"나와의 채팅에 '안녕 IRIS'라고 카톡 보내줘" 처럼 스킬 이름과 겹치는 말 + 실행을 바라는
말이 있으면 고른다. 값은 따옴표 안 글자나 "~라고" 앞 글자. 확신이 없으면 고르지 않고,
고른 뒤에도 실행 전에 사용자가 값을 확인한다 (main_window 확인 창).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# 앱 이름 ↔ 사람이 부르는 말
_APP_ALIASES = {
    "kakaotalk": ("카톡", "카카오톡", "kakao"),
    "chrome": ("크롬", "브라우저", "인터넷"),
    "notepad": ("메모장",),
    "excel": ("엑셀",),
    "winword": ("워드",),
    "line": ("라인",),
}
_ACTION = re.compile(r"(해\s*줘|해\s*주세요|해\s*봐|줘|주세요|실행|돌려|시작|보내|켜|열어|하자|해라)")
# 스킬에 대해 묻는 말 — 실행 요청이 아니다
_QUESTION = re.compile(r"(\?|뭐야|뭔데|뭐지|무엇|어떻게|알려\s*줘|설명|있어\??$|있나|되나|될까)")
_QUOTED = re.compile(r"[\"“”'‘’「『]([^\"“”'‘’」』]{1,500})[\"“”'‘’」』]")
_SAYING = re.compile(r"(\S(?:.*?\S)?)\s*(?:이?라고|하고)\s")


@dataclass
class SkillInfo:
    workflow_id: int
    name: str
    description: str = ""
    apps: str = ""
    params: list[tuple[str, str, str]] = field(default_factory=list)  # (name, label, example)


@dataclass
class SkillMatch:
    workflow_id: int
    name: str
    score: float
    params: dict[str, str]
    missing: list[str]


def _bigrams(text: str) -> set[str]:
    t = re.sub(r"[\s\W_]+", "", (text or "").lower())
    return {t[i : i + 2] for i in range(len(t) - 1)}


def _app_bonus(apps: str, message: str) -> float:
    msg = message.lower()
    for app in re.split(r"[,\s]+", (apps or "").lower()):
        key = app.removesuffix(".exe")
        for alias in _APP_ALIASES.get(key, ()):
            if alias in msg:
                return 0.25
        if key and key in msg:
            return 0.25
    return 0.0


def extract_values(message: str) -> list[str]:
    """따옴표 안 글자, 없으면 '~라고' 앞 말."""
    found = [m.group(1).strip() for m in _QUOTED.finditer(message or "")]
    if found:
        return found
    m = _SAYING.search((message or "") + " ")
    if m:
        # "나와의 채팅에 안녕이라고 보내줘" → '안녕' (앞쪽 '…에' 까지는 받는 곳이라 뺀다)
        words = m.group(1).split()
        tail: list[str] = []
        for w in reversed(words):
            if re.search(r"(에게|한테|에|께)$", w):
                break
            tail.insert(0, w)
        if tail:
            return [" ".join(tail)]
    return []


def match_skill(message: str, skills: list[SkillInfo], *, threshold: float = 0.45) -> SkillMatch | None:
    msg = (message or "").strip()
    if not msg or not skills or not _ACTION.search(msg):
        return None
    if _QUESTION.search(_QUOTED.sub(" ", msg)):
        return None
    values = extract_values(msg)
    # 따옴표 속 내용은 스킬 이름 비교에서 뺀다 (메시지 내용이 우연히 겹치지 않게)
    bare = _QUOTED.sub(" ", msg)
    msg_bi = _bigrams(bare)
    best: SkillMatch | None = None
    for sk in skills:
        name_bi = _bigrams(sk.name)
        if not name_bi:
            continue
        score = len(name_bi & msg_bi) / len(name_bi) + _app_bonus(sk.apps, bare)
        if score < threshold or (best is not None and score <= best.score):
            continue
        params: dict[str, str] = {}
        for (pname, _label, _ex), value in zip(sk.params, values):
            params[pname] = value
        missing = [p[0] for p in sk.params if p[0] not in params]
        best = SkillMatch(sk.workflow_id, sk.name, round(score, 3), params, missing)
    return best
