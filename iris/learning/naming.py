"""semantic trace / 이벤트에서 한국어 업무명·요약 자동 생성."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime

from iris.learning.models import LearningEvent, SemanticTrace


_APP_ALIASES = {
    "chrome": "Chrome",
    "msedge": "Edge",
    "firefox": "Firefox",
    "excel": "Excel",
    "winword": "Word",
    "powerpnt": "PowerPoint",
    "code": "VS Code",
    "devenv": "Visual Studio",
    "notepad": "메모장",
    "explorer": "탐색기",
    "photoshop": "Photoshop",
    "outlook": "Outlook",
    "slack": "Slack",
    "discord": "Discord",
}


def _app_label(process_name: str) -> str:
    base = (process_name or "").lower().replace(".exe", "")
    for key, label in _APP_ALIASES.items():
        if key in base:
            return label
    if base:
        return base[:1].upper() + base[1:16]
    return ""


def _action_verb_from_events(events: list[LearningEvent]) -> str:
    types = Counter(e.event_type for e in events if not e.exclude_from_trace)
    if types.get("type_text", 0) + types.get("key_down", 0) > 8:
        return "입력"
    if types.get("scroll", 0) > 5 and types.get("click", 0) < 3:
        return "스크롤 탐색"
    if types.get("drag", 0) > 0:
        return "드래그 편집"
    if types.get("click", 0) + types.get("double_click", 0) > 0:
        return "작업"
    return "업무"


def _hint_from_trace(trace: SemanticTrace | None) -> str:
    if not trace or not trace.steps:
        return ""
    texts = []
    for s in trace.steps[:8]:
        texts.append(f"{s.action} {s.observation} {s.think}")
    blob = " ".join(texts).lower()
    rules = [
        (r"github|이슈|issue", "GitHub 이슈 등록"),
        (r"csv|excel|시트", "CSV 정리 및 저장"),
        (r"resize|리사이즈|jpg|내보내", "이미지 리사이즈 및 JPG 내보내기"),
        (r"email|메일|gmail", "메일 작성 및 전송"),
        (r"search|검색", "웹 검색 및 이동"),
        (r"download|다운로드", "파일 다운로드"),
        (r"save|저장", "문서 저장"),
    ]
    for pat, name in rules:
        if re.search(pat, blob):
            return name
    # 좌표형 click 액션은 이름으로 쓰지 않음
    for s in trace.steps:
        act = (s.action or "").strip()
        if not act:
            continue
        if re.search(r"click\s*(?:at\s*)?@?\s*\(", act, re.I):
            continue
        if re.search(r"click\s*@", act, re.I) and re.search(r"\d", act):
            continue
        if re.search(r"^\s*(type|press|drag|scroll|focus)\b", act, re.I) or len(act) >= 6:
            act = re.sub(r"\s+", " ", act)
            return act[:25]
    return ""


def generate_workflow_name(
    events: list[LearningEvent],
    trace: SemanticTrace | None = None,
    *,
    now: datetime | None = None,
) -> tuple[str, str]:
    """(name, summary) — 실패 시 fallback 이름."""
    hint = _hint_from_trace(trace)
    apps = [
        _app_label(e.process_name)
        for e in events
        if not e.exclude_from_trace and e.process_name
    ]
    app = Counter(a for a in apps if a).most_common(1)
    app_name = app[0][0] if app else ""
    verb = _action_verb_from_events(events)

    if hint:
        name = hint
    elif app_name:
        name = f"{app_name} {verb}"
    else:
        ts = (now or datetime.now()).strftime("%Y-%m-%d %H%M")
        name = f"학습된 업무 {ts}"

    name = name.strip()
    if len(name) > 25:
        name = name[:25].rstrip()
    if len(name) < 4:
        ts = (now or datetime.now()).strftime("%Y-%m-%d %H%M")
        name = f"학습된 업무 {ts}"

    summary_parts = []
    if app_name:
        summary_parts.append(f"{app_name}에서")
    if hint:
        summary_parts.append(hint)
    else:
        summary_parts.append(f"{verb} 시연을 학습함")
    if trace and trace.steps:
        summary_parts.append(f"({len(trace.steps)} steps)")
    summary = " ".join(summary_parts)[:160]
    return name, summary
